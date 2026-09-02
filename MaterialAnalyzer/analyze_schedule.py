from __future__ import annotations

import argparse
from datetime import datetime

try:
    from MaterialAnalyzer.schedule_analysis import ScheduleAnalysisEngine
except ModuleNotFoundError:
    from schedule_analysis import ScheduleAnalysisEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze schedule importance and map themes/stocks")
    parser.add_argument("--date", default="", help="Scan date YYYYMMDD. Default: today")
    parser.add_argument("--top", type=int, default=30, help="Console rows to print")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scan_date = datetime.strptime(args.date, "%Y%m%d").date() if args.date else datetime.now().date()

    engine = ScheduleAnalysisEngine()
    rows, output = engine.analyze_date(scan_date)

    print("============================================")
    print("  MaterialAnalyzer V1 - Schedule Analysis")
    print("============================================")
    print(f"Scan date : {scan_date:%Y-%m-%d}")
    print(f"Rows      : {len(rows)}")
    print(f"Output    : {output}")
    print("Historical price reaction : NOT YET INCLUDED")
    print("============================================")

    if not rows:
        print("\n[INFO] No schedule candidates found. Run run_collect.bat first.")
        return 0

    print("\n[TOP SCHEDULE ANALYSIS]")
    for idx, row in enumerate(rows[: max(args.top, 0)], 1):
        stock = f" {row.name}({row.ticker})" if row.ticker else ""
        theme = row.theme or "UNMAPPED"
        print(
            f"{idx:>2}. {row.event_date} {row.priority:<12} "
            f"score={row.schedule_score:>5.1f} theme={theme:<12}{stock}"
        )
        print(f"    {row.title[:110]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
