from __future__ import annotations

import argparse
from datetime import datetime

try:
    from MaterialAnalyzer.collector import MaterialCollector
except ModuleNotFoundError:
    from collector import MaterialCollector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect raw stock-material candidates")
    parser.add_argument("--date", default="", help="Target date YYYYMMDD. Default: today")
    parser.add_argument("--days", type=int, default=2, help="Raw-source lookback calendar days")
    parser.add_argument(
        "--sources",
        default="naver,policy,dart,schedule",
        help="Comma-separated sources/stages: naver,policy,dart,schedule",
    )
    parser.add_argument("--query-limit", type=int, default=None, help="Limit Naver query rows for testing")
    parser.add_argument(
        "--schedule-lookahead",
        type=int,
        default=21,
        help="Future calendar days retained by ScheduleCollector",
    )
    parser.add_argument("--no-history", action="store_true", help="Do not append to cumulative history CSVs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_date = datetime.strptime(args.date, "%Y%m%d").date() if args.date else datetime.now().date()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    print("============================================")
    print("  MaterialAnalyzer V1 - Material Collector")
    print("============================================")
    print(f"Target date       : {target_date:%Y-%m-%d}")
    print(f"Sources/stages    : {', '.join(sources)}")
    print(f"Raw lookback days : {args.days}")
    print(f"Schedule lookahead: {args.schedule_lookahead}")
    print("Scoring           : disabled in collector V1")
    print("============================================")

    collector = MaterialCollector()
    report = collector.collect(
        target_date=target_date,
        days=max(args.days, 1),
        sources=sources,
        query_limit=args.query_limit,
        schedule_lookahead_days=max(args.schedule_lookahead, 0),
    )
    collector.save(report, target_date, append_history=not args.no_history)

    print("\n[COLLECTED]")
    for source in sources:
        print(f"  {source:<10}: {report.source_counts.get(source, 0):>5}")
    print(f"  {'raw_unique':<10}: {len(report.items):>5}")
    print(f"  {'schedules':<10}: {len(report.schedules):>5}")

    future_count = sum(1 for item in report.items if item.future_hint)
    print(f"  {'future_hint':<10}: {future_count:>5}")

    if report.warnings:
        print("\n[WARNINGS]")
        for warning in report.warnings:
            print(f"  - {warning}")

    print("\n[OUTPUT]")
    print(f"  materials snapshot : {report.snapshot_file}")
    print(f"  schedules snapshot : {report.schedule_snapshot_file}")
    if report.history_file:
        print(f"  materials history  : {report.history_file}")
    if report.schedule_history_file:
        print(f"  schedules history  : {report.schedule_history_file}")

    if report.schedules:
        print("\n[UPCOMING SCHEDULES]")
        for idx, item in enumerate(report.schedules[:20], 1):
            when = item.event_date + (f" {item.event_time}" if item.event_time else "")
            print(
                f"  {idx:>2}. {when:<16} {item.schedule_kind:<8} "
                f"conf={item.confidence:.2f} {item.title[:90]}"
            )

    if report.items:
        print("\n[TOP RAW MATERIALS]")
        for idx, item in enumerate(report.items[:15], 1):
            future = " [FUTURE]" if item.future_hint else ""
            ticker = f" [{item.ticker}]" if item.ticker else ""
            print(f"  {idx:>2}. {item.source_type:<10}{ticker}{future} {item.title[:100]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
