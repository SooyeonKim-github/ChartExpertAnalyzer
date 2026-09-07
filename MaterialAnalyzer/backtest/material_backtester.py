from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from MarketData import get_market_data_service


DEFAULT_HORIZONS = (1, 5, 10, 20, 40, 60)


@dataclass
class BacktestRunResult:
    input_rows: int
    result_rows: int
    valid_entry_rows: int
    failed_price_rows: int
    results_csv: Path
    summary_csv: Path
    errors_csv: Path
    ticker_day_results_csv: Path
    ticker_day_summary_csv: Path
    error_summary_csv: Path


def _material_score_band(value) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if score >= 85:
        return "85+"
    if score >= 70:
        return "70-84"
    if score >= 55:
        return "55-69"
    return "0-54"


def _ticker_score_band(value) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if score >= 70:
        return "70+"
    if score >= 50:
        return "50-69"
    if score >= 30:
        return "30-49"
    return "0-29"


def _direction_multiplier(value: str) -> float | None:
    text = str(value or "").upper()
    if text == "POSITIVE":
        return 1.0
    if text == "NEGATIVE":
        return -1.0
    return None


def _join_unique(series) -> str:
    seen = []
    for value in series.fillna("").astype(str):
        value = value.strip()
        if value and value not in seen:
            seen.append(value)
    return "|".join(seen)


class MaterialBacktester:
    """Point-in-time close-to-close forward return backtester.

    Entry is the close of ``market_date``. D+N means N trading bars after that close.
    The engine never silently shifts an entry. V1.1 additionally emits ticker-day
    de-duplicated results and detailed no-price classifications.
    """

    VERSION = "MATERIAL_BACKTEST_V1_1"

    def __init__(self, provider=None, horizons: Iterable[int] = DEFAULT_HORIZONS):
        self.provider = provider or get_market_data_service()
        self.horizons = tuple(sorted({int(x) for x in horizons if int(x) > 0}))
        if not self.horizons:
            raise ValueError("at least one positive forward horizon is required")

    @staticmethod
    def _load(path: str | Path) -> pd.DataFrame:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(
                f"historical backtest input not found: {source}. "
                "Run MaterialAnalyzer\\run_material_range.bat --derive-only first."
            )
        frame = pd.read_csv(source, encoding="utf-8-sig", dtype={"ticker": str, "market_date": str})
        required = {
            "market_date", "event_id", "ticker", "name", "event_type", "material_score",
            "material_status", "ticker_material_score", "positive_negative", "relation_type",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"backtest input columns missing: {missing}")
        if "backtest_eligible" in frame.columns:
            eligible = pd.to_numeric(frame["backtest_eligible"], errors="coerce").fillna(0).astype(int)
            frame = frame.loc[eligible == 1].copy()
        frame["ticker"] = frame["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
        frame["market_date"] = frame["market_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        frame = frame[frame["ticker"].str.fullmatch(r"\d{6}", na=False)].copy()
        frame = frame[frame["market_date"].str.fullmatch(r"\d{8}", na=False)].copy()
        return frame.sort_values(["ticker", "market_date", "event_id"], kind="stable").reset_index(drop=True)

    def _fetch_prices(self, ticker: str, group: pd.DataFrame) -> pd.DataFrame:
        start = pd.to_datetime(group["market_date"], format="%Y%m%d", errors="coerce").min()
        end = pd.to_datetime(group["market_date"], format="%Y%m%d", errors="coerce").max()
        if pd.isna(start) or pd.isna(end):
            raise RuntimeError("invalid market_date range")
        end = end + pd.Timedelta(days=max(120, max(self.horizons) * 2))
        prices = self.provider.get_ohlcv(ticker, start, end)
        if prices is None or prices.empty:
            raise RuntimeError("empty OHLCV")
        out = prices.copy()
        out.index = pd.to_datetime(out.index, errors="coerce").normalize()
        out = out[~out.index.isna()].sort_index()
        out = out[~out.index.duplicated(keep="last")]
        out["close"] = pd.to_numeric(out["close"], errors="coerce")
        return out.dropna(subset=["close"])

    @staticmethod
    def _missing_price_status(signal_date: pd.Timestamp, prices: pd.DataFrame) -> tuple[str, str]:
        if prices.empty:
            return "OHLCV_FAILED", "empty price frame"
        first, last = prices.index.min(), prices.index.max()
        if signal_date < first:
            return "PRE_LISTING_OR_DATA_START", f"first_price_date={first:%Y%m%d}"
        if signal_date > last:
            return "DELISTED_OR_DATA_END", f"last_price_date={last:%Y%m%d}"
        prev_dates = prices.index[prices.index < signal_date]
        next_dates = prices.index[prices.index > signal_date]
        prev_text = prev_dates.max().strftime("%Y%m%d") if len(prev_dates) else ""
        next_text = next_dates.min().strftime("%Y%m%d") if len(next_dates) else ""
        return "SUSPENDED_OR_NO_TRADING", f"no quote on market trading date; prev={prev_text}; next={next_text}"

    def _row_result(self, row: pd.Series, prices: pd.DataFrame | None, price_error: str = "") -> dict:
        record = row.to_dict()
        record["backtest_version"] = self.VERSION
        record["price_status"] = "OK"
        record["price_error"] = ""
        record["entry_date"] = ""
        record["entry_close"] = pd.NA
        record["material_score_band"] = _material_score_band(row.get("material_score"))
        record["ticker_material_score_band"] = _ticker_score_band(row.get("ticker_material_score"))
        for horizon in self.horizons:
            record[f"forward_date_D+{horizon}"] = ""
            record[f"D+{horizon}"] = pd.NA
            record[f"abs_D+{horizon}"] = pd.NA
            record[f"directional_D+{horizon}"] = pd.NA
            record[f"complete_D+{horizon}"] = 0

        if prices is None:
            record["price_status"] = "OHLCV_FAILED"
            record["price_error"] = price_error
            return record

        signal_date = pd.to_datetime(str(row["market_date"]), format="%Y%m%d", errors="coerce")
        if pd.isna(signal_date):
            record["price_status"] = "INVALID_SIGNAL_DATE"
            return record
        signal_date = signal_date.normalize()
        if signal_date not in prices.index:
            status, detail = self._missing_price_status(signal_date, prices)
            record["price_status"] = status
            record["price_error"] = detail
            return record

        location = int(prices.index.get_loc(signal_date))
        entry_close = float(prices.iloc[location]["close"])
        if entry_close <= 0:
            record["price_status"] = "INVALID_ENTRY_PRICE"
            return record

        record["entry_date"] = signal_date.strftime("%Y%m%d")
        record["entry_close"] = round(entry_close, 6)
        direction = _direction_multiplier(row.get("positive_negative", ""))
        for horizon in self.horizons:
            target = location + horizon
            if target >= len(prices):
                continue
            forward_date = prices.index[target]
            forward_close = float(prices.iloc[target]["close"])
            raw_return = (forward_close / entry_close - 1.0) * 100.0
            record[f"forward_date_D+{horizon}"] = forward_date.strftime("%Y%m%d")
            record[f"D+{horizon}"] = round(raw_return, 6)
            record[f"abs_D+{horizon}"] = round(abs(raw_return), 6)
            if direction is not None:
                record[f"directional_D+{horizon}"] = round(raw_return * direction, 6)
            record[f"complete_D+{horizon}"] = 1
        return record

    def _summary_row(self, group: pd.DataFrame, dimension: str, value: str) -> dict:
        material_score = pd.to_numeric(group["material_score"], errors="coerce")
        ticker_score = pd.to_numeric(group["ticker_material_score"], errors="coerce")
        row = {
            "dimension": dimension, "value": value, "count": int(len(group)),
            "valid_entry_count": int((group["price_status"] == "OK").sum()),
            "avg_material_score": round(float(material_score.mean()), 4) if material_score.notna().any() else pd.NA,
            "avg_ticker_material_score": round(float(ticker_score.mean()), 4) if ticker_score.notna().any() else pd.NA,
        }
        for horizon in self.horizons:
            raw = pd.to_numeric(group[f"D+{horizon}"], errors="coerce").dropna()
            abs_ret = pd.to_numeric(group[f"abs_D+{horizon}"], errors="coerce").dropna()
            directional = pd.to_numeric(group[f"directional_D+{horizon}"], errors="coerce").dropna()
            row[f"complete_D+{horizon}"] = int(len(raw))
            row[f"avg_D+{horizon}"] = round(float(raw.mean()), 4) if len(raw) else pd.NA
            row[f"median_D+{horizon}"] = round(float(raw.median()), 4) if len(raw) else pd.NA
            row[f"win_rate_D+{horizon}"] = round(float((raw > 0).mean() * 100.0), 2) if len(raw) else pd.NA
            row[f"avg_abs_D+{horizon}"] = round(float(abs_ret.mean()), 4) if len(abs_ret) else pd.NA
            row[f"directional_count_D+{horizon}"] = int(len(directional))
            row[f"avg_directional_D+{horizon}"] = round(float(directional.mean()), 4) if len(directional) else pd.NA
            row[f"directional_hit_rate_D+{horizon}"] = round(float((directional > 0).mean() * 100.0), 2) if len(directional) else pd.NA
        return row

    def _build_summary(self, results: pd.DataFrame) -> pd.DataFrame:
        if results.empty:
            return pd.DataFrame()
        records = [self._summary_row(results, "OVERALL", "ALL")]
        dimensions = [
            "material_status", "material_score_band", "ticker_material_score_band",
            "positive_negative", "event_type", "event_stage", "novelty_status",
            "relation_type", "source_id",
        ]
        if "theme" in results.columns:
            dimensions.append("theme")
        for dimension in dimensions:
            if dimension not in results.columns:
                continue
            values = results[dimension].fillna("").astype(str)
            for value in sorted(v for v in values.unique() if v):
                records.append(self._summary_row(results.loc[values == value], dimension, value))
        return pd.DataFrame(records)

    def _build_ticker_day(self, results: pd.DataFrame) -> pd.DataFrame:
        if results.empty:
            return pd.DataFrame()
        records = []
        for (_, _), group in results.groupby(["ticker", "market_date"], sort=True):
            ranked = group.copy()
            ranked["_ticker_score"] = pd.to_numeric(ranked["ticker_material_score"], errors="coerce").fillna(-1)
            ranked["_material_score"] = pd.to_numeric(ranked["material_score"], errors="coerce").fillna(-1)
            ranked = ranked.sort_values(["_ticker_score", "_material_score", "event_id"], ascending=[False, False, True], kind="stable")
            dominant = ranked.iloc[0].drop(labels=["_ticker_score", "_material_score"]).to_dict()
            dominant["event_count"] = int(len(group))
            dominant["event_ids"] = _join_unique(group["event_id"])
            dominant["event_types_all"] = _join_unique(group["event_type"])
            dominant["novelty_status_all"] = _join_unique(group["novelty_status"]) if "novelty_status" in group else ""
            dominant["relation_types_all"] = _join_unique(group["relation_type"])
            dominant["positive_negative_all"] = _join_unique(group["positive_negative"])
            if "theme" in group:
                dominant["themes_all"] = _join_unique(group["theme"])
            polarities = [x for x in group["positive_negative"].fillna("").astype(str).unique() if x]
            if len(polarities) > 1:
                dominant["positive_negative"] = "MIXED"
                for horizon in self.horizons:
                    dominant[f"directional_D+{horizon}"] = pd.NA
            records.append(dominant)
        return pd.DataFrame(records).sort_values(["market_date", "ticker"], kind="stable").reset_index(drop=True)

    @staticmethod
    def _build_error_summary(errors: pd.DataFrame) -> pd.DataFrame:
        if errors.empty:
            return pd.DataFrame(columns=["price_status", "count", "ticker_count"])
        return errors.groupby("price_status", dropna=False).agg(count=("ticker", "size"), ticker_count=("ticker", "nunique")).reset_index().sort_values(["count", "price_status"], ascending=[False, True])

    def run(self, input_path: str | Path, output_dir: str | Path, *, limit: int | None = None) -> BacktestRunResult:
        source = self._load(input_path)
        if limit is not None:
            source = source.head(max(0, int(limit))).copy()
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        print("=" * 80)
        print("MaterialBacktester V1.1 - Event + Ticker-Day Forward Returns")
        print("=" * 80)
        print(f"input         : {input_path}")
        print(f"rows          : {len(source):,}")
        print(f"tickers       : {source['ticker'].nunique():,}")
        print(f"horizons      : {','.join('D+' + str(x) for x in self.horizons)}")
        print("entry         : market_date close (no silent forward shift)")
        print("-" * 80)

        records: list[dict] = []
        ticker_total = source["ticker"].nunique()
        for ticker_index, (ticker, group) in enumerate(source.groupby("ticker", sort=True), start=1):
            prices = None
            price_error = ""
            try:
                prices = self._fetch_prices(ticker, group)
            except Exception as exc:
                price_error = f"{type(exc).__name__}: {exc}"
            for _, row in group.iterrows():
                records.append(self._row_result(row, prices, price_error))
            if ticker_index % 50 == 0 or ticker_index == ticker_total:
                print(f"  [backtest progress] tickers={ticker_index:,}/{ticker_total:,} rows={len(records):,}/{len(source):,}")

        results = pd.DataFrame(records)
        summary = self._build_summary(results)
        errors = results.loc[results["price_status"] != "OK"].copy() if not results.empty else pd.DataFrame()
        ticker_day = self._build_ticker_day(results)
        ticker_day_summary = self._build_summary(ticker_day)
        error_summary = self._build_error_summary(errors)

        results_csv = output / "material_backtest_results.csv"
        summary_csv = output / "material_backtest_summary.csv"
        errors_csv = output / "material_backtest_errors.csv"
        ticker_day_results_csv = output / "material_backtest_ticker_day_results.csv"
        ticker_day_summary_csv = output / "material_backtest_ticker_day_summary.csv"
        error_summary_csv = output / "material_backtest_error_summary.csv"
        results.to_csv(results_csv, index=False, encoding="utf-8-sig")
        summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
        errors.to_csv(errors_csv, index=False, encoding="utf-8-sig")
        ticker_day.to_csv(ticker_day_results_csv, index=False, encoding="utf-8-sig")
        ticker_day_summary.to_csv(ticker_day_summary_csv, index=False, encoding="utf-8-sig")
        error_summary.to_csv(error_summary_csv, index=False, encoding="utf-8-sig")

        valid = int((results["price_status"] == "OK").sum()) if not results.empty else 0
        failed = int((results["price_status"] != "OK").sum()) if not results.empty else 0
        print("-" * 80)
        print(f"valid_entry_rows      = {valid:,}")
        print(f"failed_price_rows     = {failed:,}")
        print(f"ticker_day_rows       = {len(ticker_day):,}")
        print(f"results               = {results_csv}")
        print(f"summary               = {summary_csv}")
        print(f"ticker_day_results    = {ticker_day_results_csv}")
        print(f"ticker_day_summary    = {ticker_day_summary_csv}")
        print(f"errors                = {errors_csv}")
        print(f"error_summary         = {error_summary_csv}")
        print("=" * 80)
        return BacktestRunResult(
            input_rows=len(source), result_rows=len(results), valid_entry_rows=valid,
            failed_price_rows=failed, results_csv=results_csv, summary_csv=summary_csv,
            errors_csv=errors_csv, ticker_day_results_csv=ticker_day_results_csv,
            ticker_day_summary_csv=ticker_day_summary_csv, error_summary_csv=error_summary_csv,
        )
