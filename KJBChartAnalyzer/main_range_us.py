from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chartsel.analysis.analyzer import ChartAnalyzer
from chartsel.backtest import range_engine
from chartsel.backtest.range_engine import (
    RangeBacktester,
    RangeBacktestParams,
    key_horizon_summary,
    parse_date_range,
)
from chartsel.backtest.range_report import save_range_backtest_excel, save_range_backtest_html
from chartsel.config import load_config
from main_range import _apply_confirmation_status, _build_status_summary

from us_market.provider import USYFinanceProvider
from us_market.universe import USUniverseService


HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="KJB US market-cap TOP N range backtest")
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--universe-csv", required=True)
    p.add_argument("--top-n", type=int, default=300)
    p.add_argument("--forward-bars", type=int, default=60)
    p.add_argument("--history-days", type=int, default=1200)
    p.add_argument("--cooldown-bars", type=int, default=0)
    p.add_argument("--min-score", type=float, default=None)
    p.add_argument("--min-technical", type=float, default=None)
    p.add_argument("--min-timing", type=float, default=None)
    p.add_argument("--max-risk", type=float, default=None)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--config", default=None)
    p.add_argument("--output-root", default=str(HERE / "results_us"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    start, end = parse_date_range(args.date_range)
    cfg = copy.deepcopy(load_config(args.config))
    cfg.setdefault("sector_strength", {})["enabled"] = False
    min_score = float(
        args.min_score if args.min_score is not None else cfg["selection"]["min_score"]
    )

    params = RangeBacktestParams(
        start_date=start,
        end_date=end,
        top_n=args.top_n,
        sort_by="market_cap",
        forward_bars=args.forward_bars,
        history_days=args.history_days,
        min_score=min_score,
        min_technical=args.min_technical,
        min_timing=args.min_timing,
        max_risk=args.max_risk,
        cooldown_bars=args.cooldown_bars,
    )

    provider = USYFinanceProvider(use_cache=not args.no_cache)
    analyzer = ChartAnalyzer(cfg)
    universe_service = USUniverseService(args.universe_csv)

    # RangeBacktester uses this module-level helper. Patch only this US process.
    range_engine._benchmark_for_market = lambda market: "^GSPC"
    runner = RangeBacktester(analyzer, provider, universe_service)

    print("=" * 78)
    print("KJB US Range Backtest")
    print("=" * 78)
    print(f"Period        : {start:%Y-%m-%d} ~ {end:%Y-%m-%d}")
    print(f"Universe      : CURRENT US market-cap TOP {args.top_n}")
    print("Benchmark     : S&P 500 (^GSPC)")
    print(f"Forward bars  : {args.forward_bars}")
    print("[WARNING] Current TOP N snapshot is reused historically; this is not PIT market-cap membership.")
    print()

    events, summary, universe, errors = runner.run(params, include_etf=False)
    events = _apply_confirmation_status(events, cfg)
    status_summary = _build_status_summary(events, args.forward_bars)

    out_dir = Path(args.output_root) / f"range_{start:%Y%m%d}_{end:%Y%m%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    events_csv = out_dir / "chart_range_events.csv"
    summary_csv = out_dir / f"chart_range_summary_D1_D{args.forward_bars}.csv"
    status_csv = out_dir / f"chart_range_status_summary_D1_D{args.forward_bars}.csv"
    universe_csv = out_dir / "universe.csv"
    errors_csv = out_dir / "errors.csv"
    workbook = out_dir / "chart_range_backtest.xlsx"
    report = out_dir / "chart_range_backtest.html"

    events.to_csv(events_csv, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    status_summary.to_csv(status_csv, index=False, encoding="utf-8-sig")
    universe.to_csv(universe_csv, index=False, encoding="utf-8-sig")
    if errors is not None and not errors.empty:
        errors.to_csv(errors_csv, index=False, encoding="utf-8-sig")

    status_counts = (
        events["Status"].value_counts() if not events.empty else pd.Series(dtype="int64")
    )
    meta = {
        "Market": "US",
        "Benchmark": "S&P 500 (^GSPC)",
        "Period": f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}",
        "Universe": f"CURRENT market_cap TOP {args.top_n}",
        "Universe warning": "Current snapshot reused historically; not point-in-time market-cap membership",
        "Forward": f"D+1 ~ D+{args.forward_bars}",
        "Selection min": min_score,
        "Cooldown": args.cooldown_bars,
        "Signals": len(events),
        "CONFIRMED": int(status_counts.get("CONFIRMED", 0)),
        "WATCH": int(status_counts.get("WATCH", 0)),
        "REJECTED": int(status_counts.get("REJECTED", 0)),
        "US price adjustment": "Yahoo Finance auto_adjust=True",
        "KR sector flow": "disabled",
    }
    save_range_backtest_excel(events, summary, universe, errors, workbook, meta)
    if not status_summary.empty:
        try:
            with pd.ExcelWriter(
                workbook, engine="openpyxl", mode="a", if_sheet_exists="replace"
            ) as writer:
                status_summary.to_excel(writer, sheet_name="Status별통계", index=False)
        except Exception as exc:
            print(f"[WARN] Status summary sheet save failed: {exc}")
    save_range_backtest_html(events, summary, report, meta)

    print("\n[Key forward returns]")
    key = key_horizon_summary(summary)
    if key.empty:
        print("No qualifying signals")
    else:
        view = key[["horizon", "valid_count", "avg_return", "median_return", "win_rate"]].copy()
        for col in ["avg_return", "median_return", "win_rate"]:
            view[col] = view[col].map(
                lambda x: "-" if pd.isna(x) else f"{float(x) * 100:.2f}%"
            )
        print(view.to_string(index=False))

    print("\n[DONE]")
    print("Events :", events_csv)
    print("Excel  :", workbook)
    print("Report :", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
