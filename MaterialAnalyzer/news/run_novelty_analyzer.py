from __future__ import annotations

import argparse
from pathlib import Path

from .disclosure_delta import DisclosureDeltaAnalyzer
from .novelty import NoveltyAnalyzer
from .storage import Database, DisclosureDeltaRepository, NoveltyRepository


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"
DEFAULT_REPORT = ROOT / "data" / "novelty_report.csv"
DEFAULT_DELTA_REPORT = ROOT / "data" / "disclosure_delta_report.csv"


def run(
    db_path: Path = DEFAULT_DB,
    output_path: Path = DEFAULT_REPORT,
    *,
    rebuild: bool = False,
    limit: int | None = None,
):
    database = Database(db_path)

    # DisclosureDelta is a prerequisite of Novelty V1.2. Run it incrementally first so
    # correction filings cannot fall through to fuzzy novelty matching as NEW_EVENT.
    delta_repository = DisclosureDeltaRepository(database)
    delta_analyzer = DisclosureDeltaAnalyzer(delta_repository)
    delta_result = delta_analyzer.run(rebuild=False, limit=None)
    delta_repository.export_report(DEFAULT_DELTA_REPORT)

    repository = NoveltyRepository(database)
    analyzer = NoveltyAnalyzer(repository)

    print("=" * 76)
    print(" NoveltyAnalyzer V1.2 - Event Family + Disclosure Revision Guard")
    print("=" * 76)
    print(f"DB      : {db_path}")
    print(f"Report  : {output_path}")
    print(f"Mode    : {'REBUILD' if rebuild else 'INCREMENTAL'}")
    print(f"Delta   : processed={delta_result.processed} revisions={delta_result.revisions} unresolved={delta_result.unresolved}")
    print("-" * 76)

    result = analyzer.run(rebuild=rebuild, limit=limit)
    report = repository.export_report(output_path)

    print(f"processed                 = {result.processed}")
    print(f"inserted                  = {result.inserted}")
    print(f"updated                   = {result.updated}")
    print(f"total_novelty             = {result.total_novelty}")
    print(f"total_families            = {result.total_families}")
    print(f"NEW_EVENT                 = {result.new_event}")
    print(f"EXISTING_EVENT_REVISION   = {result.existing_event_revision}")
    print(f"REVISION_UNRESOLVED       = {result.revision_unresolved}")
    print(f"FOLLOW_UP                 = {result.follow_up}")
    print(f"CONFIRMATION              = {result.confirmation}")
    print(f"REHASH                    = {result.rehash}")
    print(f"MARKET_REACTION           = {result.market_reaction}")
    print(f"report                    = {report}")
    print("=" * 76)
    return result


def main():
    parser = argparse.ArgumentParser(description="Rule-based NoveltyAnalyzer V1.2")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(Path(args.db), Path(args.output), rebuild=args.rebuild, limit=args.limit)


if __name__ == "__main__":
    main()
