from __future__ import annotations

import argparse
from pathlib import Path

from .disclosure_delta import DisclosureDeltaAnalyzer
from .storage import Database, DisclosureDeltaRepository


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"
DEFAULT_REPORT = ROOT / "data" / "disclosure_delta_report.csv"


def run(
    db_path: Path = DEFAULT_DB,
    output_path: Path = DEFAULT_REPORT,
    *,
    rebuild: bool = False,
    limit: int | None = None,
):
    database = Database(db_path)
    repository = DisclosureDeltaRepository(database)
    analyzer = DisclosureDeltaAnalyzer(repository)

    print("=" * 76)
    print(" DisclosureDeltaAnalyzer V1 - Correction / Revision Delta")
    print("=" * 76)
    print(f"DB      : {db_path}")
    print(f"Report  : {output_path}")
    print(f"Mode    : {'REBUILD' if rebuild else 'INCREMENTAL'}")
    print("-" * 76)

    result = analyzer.run(rebuild=rebuild, limit=limit)
    report = repository.export_report(output_path)

    print(f"processed            = {result.processed}")
    print(f"inserted             = {result.inserted}")
    print(f"updated              = {result.updated}")
    print(f"total                = {result.total}")
    print(f"originals            = {result.originals}")
    print(f"revisions            = {result.revisions}")
    print(f"revision_unresolved  = {result.unresolved}")
    print(f"increases            = {result.increases}")
    print(f"decreases            = {result.decreases}")
    print(f"minor_revision       = {result.minor}")
    print(f"report               = {report}")
    print("=" * 76)
    return result


def main():
    parser = argparse.ArgumentParser(description="DisclosureDeltaAnalyzer V1")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(Path(args.db), Path(args.output), rebuild=args.rebuild, limit=args.limit)


if __name__ == "__main__":
    main()
