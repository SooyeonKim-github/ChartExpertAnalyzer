from __future__ import annotations

import argparse
from pathlib import Path

from .disclosure_detail import DisclosureDetailAnalyzer
from .storage import Database, DisclosureDetailRepository


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"
DEFAULT_REPORT = ROOT / "data" / "disclosure_detail_report.csv"


def run(
    db_path: Path = DEFAULT_DB,
    output_path: Path = DEFAULT_REPORT,
    *,
    rebuild: bool = False,
    limit: int | None = None,
):
    database = Database(db_path)
    repository = DisclosureDetailRepository(database)
    analyzer = DisclosureDetailAnalyzer(repository)

    print("=" * 76)
    print(" DisclosureDetailEnricher V1.1 - OpenDART ORDER_CONTRACT Detail")
    print("=" * 76)
    print(f"DB      : {db_path}")
    print(f"Report  : {output_path}")
    print(f"Mode    : {'REBUILD' if rebuild else 'INCREMENTAL'}")
    print("-" * 76)

    result = analyzer.run(rebuild=rebuild, limit=limit)
    report = repository.export_report(output_path)

    print(f"processed = {result.processed}")
    print(f"inserted  = {result.inserted}")
    print(f"updated   = {result.updated}")
    print(f"success   = {result.success}")
    print(f"partial   = {result.partial}")
    print(f"failed    = {result.failed}")
    print(f"skipped   = {result.skipped}")
    print(f"total     = {result.total}")
    if result.skipped and result.processed == 0:
        print("NOTE      : OPENDART_API_KEY is not set; detail fetch was skipped.")
    print(f"report    = {report}")
    print("=" * 76)
    return result


def main():
    parser = argparse.ArgumentParser(description="OpenDART disclosure detail enricher V1.1")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(Path(args.db), Path(args.output), rebuild=args.rebuild, limit=args.limit)


if __name__ == "__main__":
    main()
