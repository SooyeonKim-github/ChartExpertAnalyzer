from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KJB_ROOT = ROOT / "KJBChartAnalyzer"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(KJB_ROOT) not in sys.path:
    sys.path.insert(0, str(KJB_ROOT))

from scripts.build_liquidity_universe import build_liquidity_universe  # noqa: E402
from chartsel.data.pykrx_provider import PykrxDataProvider  # noqa: E402
from chartsel.sector.sector_service import SectorBacktestService  # noqa: E402

from CloseBetAnalyzer.analyzer import CloseBetAnalyzer  # noqa: E402
from CloseBetAnalyzer.config import DEFAULT_CONFIG  # noqa: E402


HORIZONS = (1, 5, 10, 20, 40, 60)
CONFIRMED_STATUSES = {"STRONG_CONFIRMED", "CONFIRMED"}


def _parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    raw = str(text or "").strip().replace(" ", "")
    if "~" not in raw:
        raise ValueError("--date-range must be YYYYMMDD~YYYYMMDD")
    left, right = raw.split("~", 1)
    start = pd.to_datetime(left, format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(right, format="%Y%m%d", errors="raise").normalize()
    if start > end:
        raise ValueError(f"start date is after end date: {start.date()} > {end.date()}")
    return start, end


def _market_key(market: str) -> str:
    return "^KQ11" if "KOSDAQ" in str(market).upper() else "^KS11"


def _ticker(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _performance_metrics(full_df: pd.DataFrame, signal_date: pd.Timestamp, entry_close: float) -> dict:
    out: dict[str, float | str] = {
        "entry_date": signal_date.strftime("%Y-%m-%d"),
        "entry_close": float(entry_close),
    }
    future = full_df.loc[full_df.index > signal_date].copy()
    if future.empty or entry_close <= 0:
        out["D+1_Open_Return_Pct"] = np.nan
        for h in HORIZONS:
            out[f"D+{h}_Close_Return_Pct"] = np.nan
            out[f"MFE_{h}D_Pct"] = np.nan
            out[f"MAE_{h}D_Pct"] = np.nan
        return out

    out["D+1_Open_Return_Pct"] = (float(future.iloc[0]["Open"]) / entry_close - 1.0) * 100.0
    for h in HORIZONS:
        if len(future) < h:
            out[f"D+{h}_Close_Return_Pct"] = np.nan
            out[f"MFE_{h}D_Pct"] = np.nan
            out[f"MAE_{h}D_Pct"] = np.nan
            continue
        window = future.iloc[:h]
        out[f"D+{h}_Close_Return_Pct"] = (float(window.iloc[-1]["Close"]) / entry_close - 1.0) * 100.0
        out[f"MFE_{h}D_Pct"] = (float(pd.to_numeric(window["High"], errors="coerce").max()) / entry_close - 1.0) * 100.0
        out[f"MAE_{h}D_Pct"] = (float(pd.to_numeric(window["Low"], errors="coerce").min()) / entry_close - 1.0) * 100.0
    return out


def _summary_for(frame: pd.DataFrame, cohort: str) -> list[dict]:
    rows: list[dict] = []
    for h in HORIZONS:
        col = f"D+{h}_Close_Return_Pct"
        values = pd.to_numeric(frame.get(col, pd.Series(dtype=float)), errors="coerce").dropna()
        mfe = pd.to_numeric(frame.get(f"MFE_{h}D_Pct", pd.Series(dtype=float)), errors="coerce").dropna()
        mae = pd.to_numeric(frame.get(f"MAE_{h}D_Pct", pd.Series(dtype=float)), errors="coerce").dropna()
        rows.append(
            {
                "cohort": cohort,
                "horizon": f"D+{h}",
                "signal_count": int(len(frame)),
                "complete_count": int(len(values)),
                "avg_return_pct": float(values.mean()) if len(values) else np.nan,
                "median_return_pct": float(values.median()) if len(values) else np.nan,
                "win_rate_pct": float((values > 0).mean() * 100.0) if len(values) else np.nan,
                "avg_mfe_pct": float(mfe.mean()) if len(mfe) else np.nan,
                "avg_mae_pct": float(mae.mean()) if len(mae) else np.nan,
            }
        )
    return rows


def _build_summary(performance: pd.DataFrame, selected: pd.DataFrame, daily_top_n: int) -> pd.DataFrame:
    rows: list[dict] = []
    rows.extend(_summary_for(performance, "ALL_CONFIRMED"))
    rows.extend(_summary_for(selected, f"DAILY_TOP{daily_top_n}"))
    if not performance.empty and "status" in performance.columns:
        for status, group in performance.groupby("status"):
            rows.extend(_summary_for(group, str(status)))
    return pd.DataFrame(rows)


def _write_excel(
    path: Path,
    all_results: pd.DataFrame,
    candidates: pd.DataFrame,
    performance: pd.DataFrame,
    selected: pd.DataFrame,
    summary: pd.DataFrame,
    errors: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        all_results.to_excel(writer, sheet_name="AllResults", index=False)
        candidates.to_excel(writer, sheet_name="Candidates", index=False)
        performance.to_excel(writer, sheet_name="ConfirmedPerformance", index=False)
        selected.to_excel(writer, sheet_name="DailySelected", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
        errors.to_excel(writer, sheet_name="Errors", index=False)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CloseBetAnalyzer range backtest using point-in-time liquidity universe"
    )
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--lookback", type=int, default=20, help="liquidity universe rolling trading days")
    p.add_argument("--daily-top-n", type=int, default=5, help="confirmed names kept per signal date")
    p.add_argument("--forward-bars", type=int, default=60)
    p.add_argument("--history-days", type=int, default=520)
    p.add_argument("--request-delay", type=float, default=0.01)
    p.add_argument("--sector-info-excel", default=str(KJB_ROOT / "KOSPI_Info.xlsx"))
    p.add_argument("--output-root", default=str(HERE / "results"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    range_start, range_end = _parse_date_range(args.date_range)
    if args.top_n <= 0:
        raise ValueError("--top-n must be positive")
    if args.daily_top_n <= 0:
        raise ValueError("--daily-top-n must be positive")
    if args.forward_bars < max(HORIZONS):
        print(
            f"[WARN] --forward-bars={args.forward_bars} is below D+60; "
            "D+60 metrics may be incomplete."
        )

    out_dir = Path(args.output_root) / f"range_{range_start:%Y%m%d}_{range_end:%Y%m%d}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 92)
    print("CloseBetAnalyzer - Range Backtest")
    print("=" * 92)
    print(f"Date range       : {range_start:%Y%m%d}~{range_end:%Y%m%d}")
    print(f"Universe         : point-in-time recent {args.lookback}-day avg trading value TOP {args.top_n}")
    print("Markets          : KOSPI + KOSDAQ")
    print("Signal data      : only data available through each signal-date close")
    print("Entry assumption : signal-date close (CloseBet)")
    print(f"Daily selection  : confirmed score TOP {args.daily_top_n}")
    print(f"Forward bars     : {args.forward_bars}")
    print("=" * 92)

    print("[1/6] Building point-in-time liquidity universe...")
    membership = build_liquidity_universe(
        range_start,
        range_end,
        top_n=args.top_n,
        lookback=args.lookback,
        markets=("KOSPI", "KOSDAQ"),
        cache_dir=ROOT / "cache" / "liquidity_universe",
    )
    membership["date"] = pd.to_datetime(membership["date"]).dt.normalize()
    membership["ticker"] = membership["ticker"].map(_ticker)
    membership_path = out_dir / "liquidity_universe_daily.csv"
    membership.to_csv(membership_path, index=False, encoding="utf-8-sig")
    signal_dates = sorted(pd.Timestamp(x).normalize() for x in membership["date"].unique())
    union = (
        membership[["ticker", "name", "market"]]
        .drop_duplicates("ticker", keep="last")
        .sort_values("ticker")
        .reset_index(drop=True)
    )
    print(
        f"[INFO] universe market-days={len(signal_dates)} "
        f"union_tickers={len(union)} membership_rows={len(membership)}"
    )

    provider = PykrxDataProvider(cache_dir=HERE / "cache" / "range", use_cache=True)
    analyzer = CloseBetAnalyzer(DEFAULT_CONFIG)
    warm_start = range_start - pd.Timedelta(days=max(360, int(args.history_days)))
    future_end = range_end + pd.Timedelta(days=max(100, int(args.forward_bars) * 2 + 20))

    print("[2/6] Loading benchmark history...")
    benchmarks: dict[str, pd.DataFrame] = {}
    for key in ("^KS11", "^KQ11"):
        try:
            benchmarks[key] = provider.get_ohlcv_by_date(
                key, warm_start.strftime("%Y%m%d"), future_end.strftime("%Y%m%d")
            )
        except Exception as exc:
            print(f"[WARN] benchmark {key}: {exc}")
            benchmarks[key] = pd.DataFrame()

    print("[3/6] Loading union stock history...")
    price_cache: dict[str, pd.DataFrame] = {}
    errors: list[dict] = []
    for idx, row in union.iterrows():
        ticker = _ticker(row["ticker"])
        try:
            df = provider.get_ohlcv_by_date(
                ticker, warm_start.strftime("%Y%m%d"), future_end.strftime("%Y%m%d")
            )
            if df.empty:
                raise ValueError("empty OHLCV")
            price_cache[ticker] = df
        except Exception as exc:
            errors.append(
                {
                    "signal_date": "",
                    "ticker": ticker,
                    "name": row.get("name", ""),
                    "stage": "LOAD",
                    "error": repr(exc),
                }
            )
        done = idx + 1
        if done == 1 or done % 25 == 0 or done == len(union):
            print(f"[INFO] price load {done}/{len(union)} ready={len(price_cache)}")
        time.sleep(max(0.0, float(args.request_delay)))

    print("[4/6] Building reusable sector context...")
    sector_service = None
    try:
        sector_price_cache = {
            ticker: df.loc[df.index <= range_end].copy()
            for ticker, df in price_cache.items()
        }
        benchmark_to_signal_end = {
            key: df.loc[df.index <= range_end].copy()
            for key, df in benchmarks.items()
        }
        sector_service = SectorBacktestService(args.sector_info_excel)
        sector_service.build(
            price_cache=sector_price_cache,
            benchmark_cache=benchmark_to_signal_end,
            allowed_tickers=set(sector_price_cache),
        )
        print(f"[INFO] sector context ready scope={sector_service.aggregation_scope}")
        print(
            "[CAUTION] sector aggregation uses the range union cache; "
            "stock/date membership remains point-in-time."
        )
    except Exception as exc:
        print(f"[WARN] sector context disabled: {exc}")
        sector_service = None

    print("[5/6] Replaying each signal date...")
    all_rows: list[dict] = []
    member_groups = {
        pd.Timestamp(date).normalize(): group.sort_values("source_rank")
        for date, group in membership.groupby("date")
    }

    for date_no, signal_date in enumerate(signal_dates, start=1):
        day_members = member_groups.get(signal_date)
        if day_members is None or day_members.empty:
            continue
        day_result_count = 0
        for _, member in day_members.iterrows():
            ticker = _ticker(member["ticker"])
            full_df = price_cache.get(ticker)
            if full_df is None or full_df.empty:
                continue
            stock_history = full_df.loc[full_df.index <= signal_date].copy()
            if len(stock_history) < 130:
                continue
            if pd.Timestamp(stock_history.index[-1]).normalize() != signal_date:
                continue

            market = str(member.get("market", "KOSPI")).upper()
            market_key = _market_key(market)
            full_market = benchmarks.get(market_key, pd.DataFrame())
            market_history = full_market.loc[full_market.index <= signal_date].copy()
            if len(market_history) < 130:
                continue
            if pd.Timestamp(market_history.index[-1]).normalize() != signal_date:
                continue

            try:
                sector_ctx = (
                    sector_service.context(ticker, signal_date, market)
                    if sector_service is not None
                    else None
                )
                analyzed = analyzer.analyze(
                    ticker=ticker,
                    name=str(member.get("name", ticker)),
                    market=market,
                    stock_df=stock_history,
                    market_df=market_history,
                    sector_context=sector_ctx,
                    source_rank=int(member["source_rank"]),
                    universe_size=len(day_members),
                )
                row = analyzed.to_dict()
                row["signal_date"] = signal_date.strftime("%Y-%m-%d")
                row["universe_source_rank"] = int(member["source_rank"])
                row["universe_avg_trading_value_20d"] = member.get("avg_trading_value_20d", np.nan)
                row["universe_trading_value"] = member.get("trading_value", np.nan)
                entry_close = float(stock_history.iloc[-1]["Close"])
                row.update(_performance_metrics(full_df, signal_date, entry_close))
                all_rows.append(row)
                day_result_count += 1
            except Exception as exc:
                errors.append(
                    {
                        "signal_date": signal_date.strftime("%Y-%m-%d"),
                        "ticker": ticker,
                        "name": member.get("name", ""),
                        "stage": "ANALYZE",
                        "error": repr(exc),
                    }
                )

        if date_no == 1 or date_no % 10 == 0 or date_no == len(signal_dates):
            print(
                f"[INFO] replay {date_no}/{len(signal_dates)} "
                f"{signal_date:%Y-%m-%d} results={day_result_count} total={len(all_rows)}"
            )

    if not all_rows:
        print("[ERROR] no range results.")
        return 1

    print("[6/6] Writing performance outputs...")
    all_results = pd.DataFrame(all_rows)
    status_rank = {"STRONG_CONFIRMED": 0, "CONFIRMED": 1, "WATCH": 2, "REJECTED": 3}
    all_results["_status_rank"] = all_results["status"].map(status_rank).fillna(9)
    all_results = (
        all_results.sort_values(
            ["signal_date", "_status_rank", "score", "universe_source_rank", "ticker"],
            ascending=[True, True, False, True, True],
        )
        .drop(columns="_status_rank")
        .reset_index(drop=True)
    )

    candidates = all_results[
        all_results["status"].isin(["STRONG_CONFIRMED", "CONFIRMED", "WATCH"])
    ].copy()
    performance = all_results[all_results["status"].isin(CONFIRMED_STATUSES)].copy()

    if performance.empty:
        selected = performance.copy()
    else:
        selected = performance.copy()
        selected["_status_rank"] = selected["status"].map(
            {"STRONG_CONFIRMED": 0, "CONFIRMED": 1}
        ).fillna(9)
        selected = selected.sort_values(
            ["signal_date", "_status_rank", "score", "universe_source_rank", "ticker"],
            ascending=[True, True, False, True, True],
        )
        selected["daily_rank"] = selected.groupby("signal_date").cumcount() + 1
        selected = selected[selected["daily_rank"] <= int(args.daily_top_n)].copy()
        selected = selected.drop(columns="_status_rank").reset_index(drop=True)

    summary = _build_summary(performance, selected, int(args.daily_top_n))
    error_df = pd.DataFrame(
        errors, columns=["signal_date", "ticker", "name", "stage", "error"]
    )

    all_results.to_csv(out_dir / "range_all_results.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(out_dir / "range_candidates.csv", index=False, encoding="utf-8-sig")
    performance.to_csv(out_dir / "range_confirmed_performance.csv", index=False, encoding="utf-8-sig")
    selected.to_csv(out_dir / "range_daily_selected.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out_dir / "performance_summary.csv", index=False, encoding="utf-8-sig")
    error_df.to_csv(out_dir / "errors.csv", index=False, encoding="utf-8-sig")
    _write_excel(
        out_dir / "closebet_range_backtest.xlsx",
        all_results,
        candidates,
        performance,
        selected,
        summary,
        error_df,
    )

    counts = all_results["status"].value_counts()
    print()
    print("=" * 92)
    print("[DONE] CloseBet range backtest")
    print(f"Output     : {out_dir}")
    print(f"Signals    : {len(all_results)}")
    print(
        f"STRONG={int(counts.get('STRONG_CONFIRMED', 0))} "
        f"CONFIRMED={int(counts.get('CONFIRMED', 0))} "
        f"WATCH={int(counts.get('WATCH', 0))} "
        f"REJECTED={int(counts.get('REJECTED', 0))}"
    )
    print(f"Selected   : {len(selected)} (daily TOP {args.daily_top_n})")
    print()
    if not summary.empty:
        show = summary[
            (summary["cohort"].isin(["ALL_CONFIRMED", f"DAILY_TOP{args.daily_top_n}"]))
            & (summary["horizon"].isin(["D+1", "D+5", "D+20", "D+60"]))
        ][
            [
                "cohort",
                "horizon",
                "signal_count",
                "complete_count",
                "avg_return_pct",
                "median_return_pct",
                "win_rate_pct",
                "avg_mfe_pct",
                "avg_mae_pct",
            ]
        ]
        print(show.to_string(index=False))
    print("=" * 92)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
