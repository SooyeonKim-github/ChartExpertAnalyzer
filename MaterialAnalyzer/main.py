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
    parser.add_argument("--days", type=int, default=2, help="OpenDART lookback calendar days")
    parser.add_argument(
        "--sources",
        default="naver,policy,dart",
        help="Comma-separated sources: naver,policy,dart",
    )
    parser.add_argument("--query-limit", type=int, default=None, help="Limit Naver query rows for testing")
    parser.add_argument("--no-history", action="store_true", help="Do not append to cumulative history CSV")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_date = datetime.strptime(args.date, "%Y%m%d").date() if args.date else datetime.now().date()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    print("============================================")
    print("  MaterialAnalyzer V1 - Material Collector")
    print("============================================")
    print(f"Target date : {target_date:%Y-%m-%d}")
    print(f"Sources     : {', '.join(sources)}")
    print(f"DART days   : {args.days}")
    print("Scoring     : disabled in collector V1")
    print("============================================")

    collector = MaterialCollector()
    report = collector.collect(
        target_date=target_date,
        days=max(args.days, 1),
        sources=sources,
        query_limit=args.query_limit,
    )
    collector.save(report, target_date, append_history=not args.no_history)

    print("\n[COLLECTED]")
    for source in sources:
        print(f"  {source:<8}: {report.source_counts.get(source, 0):>5}")
    print(f"  {'unique':<8}: {len(report.items):>5}")

    future_count = sum(1 for item in report.items if item.future_hint)
    print(f"  {'future':<8}: {future_count:>5}")

    if report.warnings:
        print("\n[WARNINGS]")
        for warning in report.warnings:
            print(f"  - {warning}")

    print("\n[OUTPUT]")
    print(f"  snapshot : {report.snapshot_file}")
    if report.history_file:
        print(f"  history  : {report.history_file}")

    if report.items:
        print("\n[TOP RAW MATERIALS]")
        for idx, item in enumerate(report.items[:15], 1):
            future = " [FUTURE]" if item.future_hint else ""
            ticker = f" [{item.ticker}]" if item.ticker else ""
            print(f"  {idx:>2}. {item.source_type:<10}{ticker}{future} {item.title[:100]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
