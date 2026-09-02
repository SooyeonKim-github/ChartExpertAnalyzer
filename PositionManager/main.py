from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtester import run_range_backtest
from config import DEFAULT_CONFIG
from position_builder import build_position_plans


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _parse_range(text: str) -> tuple[str, str]:
    raw = str(text or "").strip().replace("-", "").replace(" ", "")
    if "~" not in raw:
        raise ValueError("date range must be YYYYMMDD~YYYYMMDD")
    start, end = raw.split("~", 1)
    pd.to_datetime(start, format="%Y%m%d", errors="raise")
    pd.to_datetime(end, format="%Y%m%d", errors="raise")
    return start, end


def _print_summary(summary: pd.DataFrame) -> None:
    if summary.empty:
        print("[INFO] No position backtest rows.")
        return
    cols = [
        "analyzer", "count", "entered_count", "entry_cancelled_count", "expired_count",
        "entry_rate_pct", "win_rate_pct", "avg_strategy_return_pct",
        "avg_invested_weight_pct", "avg_baseline_d20_pct",
        "avg_alpha_vs_baseline_d20_pct", "cancelled_avg_baseline_d20_pct",
    ]
    view = summary[[c for c in cols if c in summary.columns]].copy()
    print()
    print("=" * 130)
    print("  DYNAMIC POSITION MANAGER BACKTEST SUMMARY")
    print("=" * 130)
    print(view.to_string(index=False, float_format=lambda x: f"{x:8.2f}"))
    print("=" * 130)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dynamic daily-decision scale-in PositionManager")
    sub = parser.add_subparsers(dest="command", required=True)

    screen = sub.add_parser("screen", help="Build dynamic plans for latest confirmed screening date")
    screen.add_argument("--input", default=str(ROOT / "results" / "confirmed_candidates.csv"))
    screen.add_argument("--output", default=str(HERE / "results" / "position_plans.csv"))

    rng = sub.add_parser("range", help="Backtest dynamic PositionManager on range confirmed signals")
    rng.add_argument("--date-range", required=True)

    args = parser.parse_args()
    cfg = DEFAULT_CONFIG
    cfg.validate()

    if args.command == "screen":
        out = build_position_plans(Path(args.input), Path(args.output), cfg)
        print(f"[DONE] Dynamic position plans: {len(out)} -> {args.output}")
        if not out.empty:
            cols = [
                "signal_date", "analyzer", "ticker", "name",
                "evaluation_date", "daily_entry_decision", "daily_entry_score",
                "stage1_status", "stage2_target_price", "stop_price",
            ]
            view = out[[c for c in cols if c in out.columns]].copy()
            print(view.to_string(index=False, float_format=lambda x: f"{x:8.2f}"))
        return 0

    start, end = _parse_range(args.date_range)
    range_key = f"{start}_{end}"
    input_path = ROOT / "results" / f"range_{range_key}" / "confirmed_candidates.csv"
    output_dir = HERE / "results" / f"range_{range_key}"
    detail, summary = run_range_backtest(
        input_path=input_path,
        output_dir=output_dir,
        cfg=cfg,
        start=start,
        end=end,
    )
    print(f"[DONE] Position backtest rows: {len(detail)} -> {output_dir / 'position_backtest.csv'}")
    print(f"[DONE] Daily decision log -> {output_dir / 'daily_decisions.csv'}")
    print(f"[DONE] Position summary -> {output_dir / 'position_backtest_summary.csv'}")
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
