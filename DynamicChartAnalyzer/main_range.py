from __future__ import annotations

"""Canonical DynamicChartAnalyzer range backtest.

This file is the current Korean-market range runner. It preserves the lecture timing
logic (RSI -> MACD -> Ichimoku, Stage1 -> Stage2 -> Stage3, fixed 1:2:7 entry plan)
and applies the current V2.2 secondary LONG quality overlay.

There are no versioned main_range runners anymore. Keep this file as the single
source of truth for Korean Dynamic range backtests.
"""

import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from dynamic_chart_analyzer import DynamicChartAnalyzer, StrategyConfig
from dynamic_chart_analyzer.long_v2 import (
    BASE_EVENT_FEATURE_COLUMNS,
    BENCHMARK_PROXY,
    add_long_v2_features,
    add_rs_percentiles,
    prepare_market_features,
)
from dynamic_chart_analyzer.long_v22 import score_long_events
from dynamic_chart_analyzer.providers import load_pykrx

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
KJB_ROOT = PROJECT_ROOT / "KJBChartAnalyzer"
KJB_INFO_EXCEL = KJB_ROOT / "KOSPI_Info.xlsx"


@dataclass(frozen=True)
class RangeParams:
    start: pd.Timestamp
    end: pd.Timestamp
    top_n: int
    sort_by: str
    forward_bars: int
    history_days: int
    capital: float
    use_risk_cap: bool
    use_stop: bool
    include_dynamic_rsi: bool


def parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    raw = str(text or "").strip().replace(" ", "")
    if "~" not in raw:
        raise ValueError("Date range must be YYYYMMDD~YYYYMMDD, e.g. 20260401~20260531")
    left, right = raw.split("~", 1)
    start = pd.to_datetime(left, format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(right, format="%Y%m%d", errors="raise").normalize()
    if start > end:
        raise ValueError(f"Start date is after end date: {start.date()} > {end.date()}")
    return start, end


def _import_pykrx():
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx is not installed. Run: pip install -r requirements.txt") from exc
    return stock


def _latest_market_date(_stock, requested: pd.Timestamp, max_lookback_days: int = 30) -> str:
    """Resolve latest KRX trading date from Samsung Electronics daily OHLCV.

    Uses the same stable per-ticker path as KJB/Swing instead of the fragile
    all-ticker snapshot endpoint.
    """
    requested = min(pd.Timestamp(requested).normalize(), pd.Timestamp.today().normalize())
    start = requested - pd.Timedelta(days=max_lookback_days)

    try:
        cal = load_pykrx(
            "005930",
            start.strftime("%Y%m%d"),
            requested.strftime("%Y%m%d"),
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not resolve KRX trading date from 005930 daily OHLCV "
            f"at/before {requested.date()}: {type(exc).__name__}: {exc}"
        ) from exc

    if cal is None or cal.empty:
        raise RuntimeError(
            f"Could not resolve KRX trading date at/before {requested.date()}: "
            "005930 daily OHLCV is empty"
        )

    dates = pd.to_datetime(cal.index, errors="coerce")
    dates = dates[dates.notna()]
    dates = dates[dates.normalize() <= requested]
    if not len(dates):
        raise RuntimeError(
            f"Could not resolve KRX trading date at/before {requested.date()} "
            "from 005930 daily OHLCV"
        )
    return pd.Timestamp(dates.max()).strftime("%Y%m%d")


def _get_universe(snapshot_date: str, top_n: int, sort_by: str) -> pd.DataFrame:
    """Build current KOSPI+KOSDAQ TOP-N with KJB TickerUniverseService."""
    if not KJB_ROOT.exists():
        raise RuntimeError(f"KJBChartAnalyzer folder not found: {KJB_ROOT}")
    if not KJB_INFO_EXCEL.exists():
        raise RuntimeError(f"KOSPI_Info.xlsx not found: {KJB_INFO_EXCEL}")

    if str(KJB_ROOT) not in sys.path:
        sys.path.insert(0, str(KJB_ROOT))

    from chartsel.universe.ticker_universe_service import TickerUniverseService

    service = TickerUniverseService(KJB_INFO_EXCEL)
    infos = service.get_universe(top_n=top_n, sort_by=sort_by, include_etf=False)
    if not infos:
        raise RuntimeError(
            f"KJB/Swing-style universe is empty: sort_by={sort_by}, top_n={top_n}"
        )

    rows = [
        {
            "ticker": info.ticker,
            "source_rank": info.source_rank,
            "name": info.name,
            "market": info.market,
            "market_cap": info.market_cap,
            "trading_value": info.trading_value,
            "volume": info.volume,
        }
        for info in infos
    ]
    universe = pd.DataFrame(rows)
    print(
        f"[INFO] Universe source: {KJB_INFO_EXCEL} | "
        f"KJB TickerUniverseService | reference trading date={snapshot_date}"
    )
    print(
        "[INFO] Universe rule: current KOSPI_Info.xlsx snapshot; "
        "no pykrx all-ticker OHLCV/market-cap snapshot call"
    )
    return universe


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def _direction(action: str) -> int:
    return -1 if str(action).startswith("SHORT_") else 1


def _add_forward_metrics(event: dict, price_df: pd.DataFrame, forward_bars: int) -> dict:
    out = dict(event)
    signal_date = pd.Timestamp(out["signal_date"])
    entry = float(out["entry_price"])
    direction = int(out["direction"])

    positions = np.flatnonzero(price_df.index.normalize() == signal_date.normalize())
    if len(positions) == 0 or not math.isfinite(entry) or entry <= 0:
        for h in range(1, forward_bars + 1):
            out[f"D+{h}"] = np.nan
        out[f"MFE_D+{forward_bars}"] = np.nan
        out[f"MAE_D+{forward_bars}"] = np.nan
        out["forward_available_bars"] = 0
        out["forward_complete"] = False
        return out

    idx = int(positions[0])
    available = max(0, min(forward_bars, len(price_df) - idx - 1))
    for h in range(1, forward_bars + 1):
        if idx + h < len(price_df):
            future = float(price_df["close"].iloc[idx + h])
            raw = future / entry - 1.0
            out[f"D+{h}"] = direction * raw
        else:
            out[f"D+{h}"] = np.nan

    out["forward_available_bars"] = available
    out["forward_complete"] = bool(available >= forward_bars)
    if available:
        fwd = price_df.iloc[idx + 1 : idx + available + 1]
        if direction > 0:
            out[f"MFE_D+{forward_bars}"] = float(fwd["high"].max() / entry - 1.0)
            out[f"MAE_D+{forward_bars}"] = float(fwd["low"].min() / entry - 1.0)
        else:
            out[f"MFE_D+{forward_bars}"] = float(1.0 - fwd["low"].min() / entry)
            out[f"MAE_D+{forward_bars}"] = float(1.0 - fwd["high"].max() / entry)
    else:
        out[f"MFE_D+{forward_bars}"] = np.nan
        out[f"MAE_D+{forward_bars}"] = np.nan
    return out


def _build_summary(events: pd.DataFrame, forward_bars: int) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["side", "stage", "count"])

    horizons = [h for h in [1, 5, 10, 20, 40, 60] if h <= forward_bars]
    rows: list[dict] = []
    for (side, stage), g in events.groupby(["side", "stage"], dropna=False):
        row: dict[str, object] = {
            "side": side,
            "stage": int(stage),
            "count": int(len(g)),
            "complete_count": int(g["forward_complete"].fillna(False).sum()),
        }
        for h in horizons:
            col = f"D+{h}"
            vals = pd.to_numeric(g[col], errors="coerce").dropna()
            row[f"avg_{col}"] = float(vals.mean()) if len(vals) else np.nan
            row[f"median_{col}"] = float(vals.median()) if len(vals) else np.nan
            row[f"win_rate_{col}"] = float((vals > 0).mean()) if len(vals) else np.nan
        mfe_col = f"MFE_D+{forward_bars}"
        mae_col = f"MAE_D+{forward_bars}"
        row[f"avg_{mfe_col}"] = float(pd.to_numeric(g[mfe_col], errors="coerce").mean())
        row[f"avg_{mae_col}"] = float(pd.to_numeric(g[mae_col], errors="coerce").mean())
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["side", "stage"]).reset_index(drop=True)


def _build_long_summary(events: pd.DataFrame, forward_bars: int) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["long_quality_label", "stage", "count"])

    long_df = events[events["side"].eq("LONG")].copy()
    if long_df.empty:
        return pd.DataFrame(columns=["long_quality_label", "stage", "count"])

    horizons = [h for h in [1, 5, 10, 20, 40, 60] if h <= forward_bars]
    rows: list[dict] = []
    label_order = {"CONFIRMED": 0, "WATCH": 1, "REJECT": 2}

    for (label, stage), g in long_df.groupby(["long_quality_label", "stage"], dropna=False):
        row: dict[str, object] = {
            "long_quality_label": label,
            "stage": int(stage),
            "count": int(len(g)),
            "complete_count": int(g["forward_complete"].fillna(False).sum()),
            "avg_lecture_score": float(pd.to_numeric(g["lecture_score"], errors="coerce").mean()),
            "avg_quality_score": float(pd.to_numeric(g["quality_score"], errors="coerce").mean()),
            "avg_combined_score": float(pd.to_numeric(g["combined_score"], errors="coerce").mean()),
        }
        for h in horizons:
            col = f"D+{h}"
            vals = pd.to_numeric(g[col], errors="coerce").dropna()
            row[f"avg_{col}"] = float(vals.mean()) if len(vals) else np.nan
            row[f"median_{col}"] = float(vals.median()) if len(vals) else np.nan
            row[f"win_rate_{col}"] = float((vals > 0).mean()) if len(vals) else np.nan
        mfe_col = f"MFE_D+{forward_bars}"
        mae_col = f"MAE_D+{forward_bars}"
        row[f"avg_{mfe_col}"] = float(pd.to_numeric(g[mfe_col], errors="coerce").mean())
        row[f"avg_{mae_col}"] = float(pd.to_numeric(g[mae_col], errors="coerce").mean())
        rows.append(row)

    out = pd.DataFrame(rows)
    out["_label_order"] = out["long_quality_label"].map(label_order).fillna(99)
    return (
        out.sort_values(["_label_order", "stage"])
        .drop(columns="_label_order")
        .reset_index(drop=True)
    )


def _scalar(value):
    if isinstance(value, pd.Series):
        if value.empty:
            return np.nan
        value = value.iloc[-1]
    if value is pd.NA:
        return np.nan
    return value


def _write_excel(
    path: Path,
    events: pd.DataFrame,
    summary: pd.DataFrame,
    long_summary: pd.DataFrame,
    long_candidates: pd.DataFrame,
    universe: pd.DataFrame,
    errors: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        long_summary.to_excel(writer, sheet_name="LongSummary", index=False)
        long_candidates.to_excel(writer, sheet_name="LongCandidates", index=False)
        events.to_excel(writer, sheet_name="Events", index=False)
        universe.to_excel(writer, sheet_name="Universe", index=False)
        errors.to_excel(writer, sheet_name="Errors", index=False)


def _load_market_feature_map(
    universe: pd.DataFrame,
    history_start: str,
    forward_end: str,
) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    feature_map: dict[str, pd.DataFrame] = {}
    errors: list[dict] = []

    markets = sorted({str(x).upper() for x in universe.get("market", pd.Series(dtype=str)).dropna()})
    for market in markets:
        proxy = BENCHMARK_PROXY.get(market)
        if not proxy:
            errors.append(
                {
                    "ticker": f"BENCHMARK:{market}",
                    "name": "",
                    "error": f"No benchmark proxy configured for market={market}",
                }
            )
            continue
        try:
            raw = _normalize_ohlcv(load_pykrx(proxy, history_start, forward_end))
            feature_map[market] = prepare_market_features(raw)
            print(f"[QUALITY] Market proxy {market}: {proxy} ({len(raw):,} bars)")
        except Exception as exc:
            errors.append(
                {
                    "ticker": f"BENCHMARK:{market}",
                    "name": proxy,
                    "error": repr(exc),
                }
            )
            print(f"[WARN] Market proxy failed {market}/{proxy}: {exc}")
    return feature_map, errors


def run_range(args) -> int:
    start, end = parse_date_range(args.date_range)
    params = RangeParams(
        start=start,
        end=end,
        top_n=args.top_n,
        sort_by=args.sort_by,
        forward_bars=args.forward_bars,
        history_days=args.history_days,
        capital=args.capital,
        use_risk_cap=args.risk_cap,
        use_stop=not args.no_stop,
        include_dynamic_rsi=args.dynamic_rsi,
    )

    stock = _import_pykrx()
    snapshot = _latest_market_date(stock, end)
    universe = _get_universe(snapshot, params.top_n, params.sort_by)

    history_start = (start - pd.Timedelta(days=params.history_days)).strftime("%Y%m%d")
    forward_end = (end + pd.Timedelta(days=max(120, params.forward_bars * 3))).strftime("%Y%m%d")

    market_feature_map, benchmark_errors = _load_market_feature_map(
        universe, history_start, forward_end
    )

    cfg = StrategyConfig(
        total_capital=params.capital,
        use_two_percent_risk_cap=params.use_risk_cap,
        use_protective_stop=params.use_stop,
    )
    analyzer = DynamicChartAnalyzer(cfg, include_dynamic_rsi=params.include_dynamic_rsi)

    print("=" * 78)
    print("DynamicChartAnalyzer Range Backtest - CURRENT")
    print("=" * 78)
    print(f"Date range       : {start:%Y%m%d}~{end:%Y%m%d}")
    print(f"Universe snapshot: {snapshot}")
    print(f"Universe TOP N   : {len(universe)}")
    print(f"Sort by          : {params.sort_by}")
    print(f"Forward bars     : {params.forward_bars}")
    print(f"Capital          : {params.capital:,.0f} KRW (Stage 1/2/3 = 1:2:7)")
    print("Lecture timing   : RSI -> MACD -> Ichimoku")
    print("Quality weights  : RS25 / Trend20 / Structure15 / Volume15 / Market10 / Risk15")
    print("Market context   : REVERSAL / NEUTRAL / TREND; no directional reverse scoring")
    print(
        f"Quality labels   : CONFIRMED >= {args.confirmed_score:g}, "
        f"WATCH >= {args.watch_score:g}"
    )
    print("Daily LONG rank  : quality_score first, lecture_score tie-breaker")
    print("Benchmark proxy  : KOSPI=069500 / KOSDAQ=229200")
    print()

    event_rows: list[dict] = []
    error_rows: list[dict] = list(benchmark_errors)
    rs_panel_rows: list[pd.DataFrame] = []

    for n, rec in enumerate(universe.itertuples(index=False), start=1):
        ticker = str(rec.ticker).zfill(6)
        name = str(rec.name or "")
        market = str(getattr(rec, "market", "") or "").upper()
        print(f"[{n:03d}/{len(universe):03d}] {ticker} {name}")
        try:
            raw = _normalize_ohlcv(load_pykrx(ticker, history_start, forward_end))
            analyzed, events = analyzer.analyze(raw)
            enriched = add_long_v2_features(analyzed, market_feature_map.get(market))

            panel_slice = enriched.loc[
                (enriched.index >= start) & (enriched.index <= end), ["rs_20", "rs_60"]
            ].copy()
            if not panel_slice.empty:
                panel_slice = panel_slice.reset_index()
                panel_slice = panel_slice.rename(columns={panel_slice.columns[0]: "signal_date"})
                panel_slice["ticker"] = ticker
                rs_panel_rows.append(panel_slice[["signal_date", "ticker", "rs_20", "rs_60"]])

            if events.empty:
                continue

            e = events.copy()
            e["date"] = pd.to_datetime(e["date"])
            e = e[(e["date"] >= start) & (e["date"] <= end)]
            e = e[e["action"].astype(str).str.contains("_ENTRY_STAGE_", regex=False)]
            if e.empty:
                continue

            for _, row in e.iterrows():
                action = str(row["action"])
                side = "SHORT" if action.startswith("SHORT_") else "LONG"
                signal_date = pd.Timestamp(row["date"])
                feature_row = enriched.loc[signal_date]

                base = {
                    "signal_date": signal_date,
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "source_rank": int(rec.source_rank),
                    "sort_by": params.sort_by,
                    "side": side,
                    "direction": _direction(action),
                    "stage": int(row.get("stage", 0)),
                    "action": action,
                    "entry_price": float(row["price"]),
                    "entry_amount_krw": float(row.get("amount_krw", np.nan)),
                    "cumulative_invested_krw": float(row.get("cumulative_invested_krw", np.nan)),
                    "weighted_entry_price": float(row.get("weighted_entry_price", np.nan)),
                    "stop_price": row.get("stop_price", np.nan),
                    "reference_target_price": row.get("reference_target_price", np.nan),
                    "risk_capped": bool(row.get("risk_capped", False)),
                }
                for col in BASE_EVENT_FEATURE_COLUMNS:
                    base[col] = _scalar(feature_row.get(col, np.nan))

                event_rows.append(_add_forward_metrics(base, raw, params.forward_bars))
        except Exception as exc:
            error_rows.append({"ticker": ticker, "name": name, "error": repr(exc)})
            print(f"  [WARN] {exc}")
        time.sleep(max(0.0, float(args.request_delay)))

    events_df = pd.DataFrame(event_rows)

    if rs_panel_rows:
        rs_panel = add_rs_percentiles(pd.concat(rs_panel_rows, ignore_index=True))
        rs_lookup = rs_panel[
            ["signal_date", "ticker", "rs_percentile_20", "rs_percentile_60"]
        ].drop_duplicates(["signal_date", "ticker"], keep="last")
    else:
        rs_lookup = pd.DataFrame(
            columns=["signal_date", "ticker", "rs_percentile_20", "rs_percentile_60"]
        )

    if not events_df.empty:
        events_df["signal_date"] = pd.to_datetime(events_df["signal_date"])
        events_df = events_df.merge(
            rs_lookup,
            on=["signal_date", "ticker"],
            how="left",
            validate="many_to_one",
        )
        events_df = score_long_events(
            events_df,
            confirmed_score=float(args.confirmed_score),
            watch_score=float(args.watch_score),
        )
        events_df = events_df.sort_values(["signal_date", "ticker", "stage"]).reset_index(drop=True)
        events_df["daily_stage_rank"] = (
            events_df.groupby(["signal_date", "side", "stage"])["source_rank"]
            .rank(method="first")
            .astype(int)
        )
        events_df["is_daily_top5_long"] = (
            events_df["side"].eq("LONG")
            & events_df["long_quality_label"].isin(["CONFIRMED", "WATCH"])
            & pd.to_numeric(events_df["daily_long_rank"], errors="coerce").le(5)
        )

    summary_df = _build_summary(events_df, params.forward_bars)
    long_summary_df = _build_long_summary(events_df, params.forward_bars)
    errors_df = pd.DataFrame(error_rows, columns=["ticker", "name", "error"])

    long_mask = (
        events_df["side"].eq("LONG")
        if "side" in events_df.columns
        else pd.Series(False, index=events_df.index)
    )
    quality_mask = (
        events_df["long_quality_label"].isin(["CONFIRMED", "WATCH"])
        if "long_quality_label" in events_df.columns
        else pd.Series(False, index=events_df.index)
    )
    long_candidates_df = events_df[long_mask & quality_mask].copy()
    if not long_candidates_df.empty:
        long_candidates_df = long_candidates_df.sort_values(
            ["signal_date", "daily_long_rank", "stage"], ascending=[True, True, False]
        )

    out_dir = Path(args.output_root) / f"range_{start:%Y%m%d}_{end:%Y%m%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "dynamic_range_events.csv"
    summary_path = out_dir / "dynamic_range_summary.csv"
    long_summary_path = out_dir / "dynamic_long_v2_summary.csv"
    candidates_path = out_dir / "dynamic_long_v2_candidates.csv"
    universe_path = out_dir / "universe.csv"
    errors_path = out_dir / "errors.csv"
    excel_path = out_dir / "dynamic_range_backtest.xlsx"

    events_df.to_csv(events_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    long_summary_df.to_csv(long_summary_path, index=False, encoding="utf-8-sig")
    long_candidates_df.to_csv(candidates_path, index=False, encoding="utf-8-sig")
    universe.to_csv(universe_path, index=False, encoding="utf-8-sig")
    errors_df.to_csv(errors_path, index=False, encoding="utf-8-sig")
    _write_excel(
        excel_path,
        events_df,
        summary_df,
        long_summary_df,
        long_candidates_df,
        universe,
        errors_df,
    )

    print()
    print("=" * 78)
    print("Dynamic range backtest finished")
    print("=" * 78)
    print(f"Entry events : {len(events_df):,}")
    print(f"LONG events  : {int(events_df['side'].eq('LONG').sum()) if not events_df.empty else 0:,}")
    if not events_df.empty:
        labels = events_df.loc[
            events_df["side"].eq("LONG"), "long_quality_label"
        ].value_counts()
        print(
            "LONG labels  : "
            + " / ".join(
                f"{k}={int(labels.get(k, 0))}" for k in ["CONFIRMED", "WATCH", "REJECT"]
            )
        )
    print(f"Errors       : {len(errors_df):,}")
    print(f"Saved        : {excel_path}")
    print(f"Saved        : {events_path}")
    print(f"Saved        : {long_summary_path}")
    print(f"Saved        : {candidates_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="DynamicChartAnalyzer TOP-N range backtest (current V2.2 logic)"
    )
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--top-n", type=int, default=100, help="Universe size; default 100")
    p.add_argument(
        "--sort-by",
        choices=["market_cap", "trading_value", "volume"],
        default="market_cap",
    )
    p.add_argument("--forward-bars", type=int, default=60, help="Forward performance trading bars")
    p.add_argument("--history-days", type=int, default=450, help="Calendar history before start")
    p.add_argument("--capital", type=float, default=10_000_000, help="Capital in KRW; fixed 1:2:7 split")
    p.add_argument("--risk-cap", action="store_true", help="Enable optional 2%% account-risk cap")
    p.add_argument("--no-stop", action="store_true", help="Disable protective swing stop")
    p.add_argument("--dynamic-rsi", action="store_true", help="Include experimental Dynamic RSI")
    p.add_argument("--request-delay", type=float, default=0.05, help="Delay between ticker requests")
    p.add_argument("--output-root", default=str(ROOT / "results"))
    p.add_argument(
        "--confirmed-score",
        "--v2-confirmed-score",
        dest="confirmed_score",
        type=float,
        default=70.0,
        help="LONG CONFIRMED quality threshold; default 70",
    )
    p.add_argument(
        "--watch-score",
        "--v2-watch-score",
        dest="watch_score",
        type=float,
        default=55.0,
        help="LONG WATCH quality threshold; default 55",
    )
    return p


if __name__ == "__main__":
    raise SystemExit(run_range(build_parser().parse_args()))
