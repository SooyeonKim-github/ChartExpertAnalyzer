from __future__ import annotations

import argparse
from pathlib import Path

from .storage import Database, TickerLinkRepository
from .ticker_linking import TickerLinker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"
DEFAULT_REFERENCE = ROOT / "data" / "reference"
DEFAULT_REPORT = ROOT / "data" / "ticker_link_report.csv"
DEFAULT_UNRESOLVED = ROOT / "data" / "ticker_link_unresolved.csv"


def run(db_path=DEFAULT_DB, reference_dir=DEFAULT_REFERENCE, output_path=DEFAULT_REPORT,
        unresolved_path=DEFAULT_UNRESOLVED, *, rebuild=False, limit=None):
    database = Database(db_path)
    repository = TickerLinkRepository(database)
    linker = TickerLinker(repository, reference_dir)

    print("=" * 76)
    print(" TickerLinker V1 - Direct / Exact Company / Evidence / Theme")
    print("=" * 76)
    print(f"DB         : {db_path}")
    print(f"Reference  : {reference_dir}")
    print(f"Report     : {output_path}")
    print(f"Unresolved : {unresolved_path}")
    print(f"Mode       : {'REBUILD' if rebuild else 'INCREMENTAL'}")
    print("-" * 76)

    result = linker.run(rebuild=rebuild, limit=limit)
    report = repository.export_report(output_path)
    unresolved = repository.export_unresolved(unresolved_path)

    print(f"processed         = {result.processed}")
    print(f"linked_events     = {result.linked_events}")
    print(f"unresolved_events = {result.unresolved_events}")
    print(f"total_events      = {result.total_events}")
    print(f"total_links       = {result.total_links}")
    print(f"DIRECT            = {result.direct}")
    print(f"SUPPLIER          = {result.supplier}")
    print(f"CUSTOMER          = {result.customer}")
    print(f"SECTOR            = {result.sector}")
    print(f"THEME             = {result.theme}")
    print(f"report             = {report}")
    print(f"unresolved         = {unresolved}")
    print("=" * 76)
    return result


def main():
    parser = argparse.ArgumentParser(description="Deterministic TickerLinker V1")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--unresolved", default=str(DEFAULT_UNRESOLVED))
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(
        Path(args.db), Path(args.reference), Path(args.output), Path(args.unresolved),
        rebuild=args.rebuild, limit=args.limit,
    )


if __name__ == "__main__":
    main()
