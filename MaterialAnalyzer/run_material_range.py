from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .history import HistoricalMaterialPipeline, HistoricalRangeConfig


ROOT = Path(__file__).resolve().parents[1]


def _parse_range(value: str):
    text = (value or "").strip()
    if "~" not in text:
        raise ValueError("date range must be YYYYMMDD~YYYYMMDD")
    left, right = [part.strip() for part in text.split("~", 1)]
    start = datetime.strptime(left, "%Y%m%d").date()
    end = datetime.strptime(right, "%Y%m%d").date()
    if end < start:
        raise ValueError("end date must be >= start date")
    return start, end


def main():
    parser = argparse.ArgumentParser(description="HistoricalMaterialRangeCollector V1.1")
    parser.add_argument("--date-range", default="")
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--chunk-days", type=int, default=7)
    parser.add_argument("--government-max-pages", type=int, default=500)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--collect-only", "--collection-only", dest="collect_only", action="store_true",
                      help="collect/resume raw history only; skip derived rebuild")
    mode.add_argument("--derive-only", "--no-collect", dest="derive_only", action="store_true",
                      help="reuse raw history and rebuild derived layers only")
    parser.add_argument("--strict", action="store_true", help="stop on first failed source/chunk")
    args = parser.parse_args()

    print("=" * 80)
    print("MaterialAnalyzer - HistoricalMaterialRangeCollector V1.1")
    print("Fast DART Bulk / Point-in-Time / Resume / Prefiltered Derived Rebuild")
    print("=" * 80)
    date_range = args.date_range.strip()
    if not date_range:
        print("Example: 20260101~20260630")
        date_range = input("Date range YYYYMMDD~YYYYMMDD: ").strip()
    start, end = _parse_range(date_range)
    config = HistoricalRangeConfig(
        requested_start=start,
        requested_end=end,
        warmup_days=args.warmup_days,
        chunk_days=args.chunk_days,
        government_max_pages=args.government_max_pages,
        continue_on_error=not args.strict,
    )
    config.validate()
    collect = not args.derive_only
    derived = not args.collect_only
    print(f"Requested     : {config.requested_start} ~ {config.requested_end}")
    print(f"Context start : {config.context_start} (warmup={config.warmup_days}d)")
    print(f"Chunk days    : {config.chunk_days}")
    print(f"Collection    : {'ON' if collect else 'OFF (derive-only)'}")
    print(f"Derived       : {'REBUILD' if derived else 'OFF (collect-only)'}")
    print("=" * 80)

    pipeline = HistoricalMaterialPipeline(ROOT, config)
    result = pipeline.run(collect=collect, reprocess_derived=derived)
    print("\n" + "=" * 80)
    print(f"STATUS        : {result.status}")
    print(f"failed_chunks : {result.failed_chunks}")
    print(f"history_rows  : {result.history_rows}")
    print(f"backtest_rows : {result.backtest_rows}")
    print(f"history_csv   : {result.history_csv}")
    print(f"backtest_csv  : {result.backtest_csv}")
    print(f"coverage_csv  : {result.coverage_csv}")
    print("=" * 80)


if __name__ == "__main__":
    main()
