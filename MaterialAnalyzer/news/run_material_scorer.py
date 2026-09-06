from __future__ import annotations

import argparse
from pathlib import Path

from .scoring import MaterialScorer
from .storage import Database, MaterialScoreRepository


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"
DEFAULT_REPORT = ROOT / "data" / "material_score_report.csv"


def run(
    db_path: Path = DEFAULT_DB,
    output_path: Path = DEFAULT_REPORT,
    *,
    rebuild: bool = False,
    limit: int | None = None,
):
    database = Database(db_path)
    repository = MaterialScoreRepository(database)
    scorer = MaterialScorer(repository)

    print("=" * 76)
    print(" MaterialScorer V1.1 - Deterministic 100 Point Material Score")
    print(" Routine Governance Impact Guard")
    print("=" * 76)
    print(f"DB      : {db_path}")
    print(f"Report  : {output_path}")
    print(f"Mode    : {'REBUILD' if rebuild else 'INCREMENTAL'}")
    print("-" * 76)

    result = scorer.run(rebuild=rebuild, limit=limit)
    report = repository.export_report(output_path)

    print(f"processed      = {result.processed}")
    print(f"inserted       = {result.inserted}")
    print(f"updated        = {result.updated}")
    print(f"total_scores   = {result.total_scores}")
    print(f"STRONG         = {result.strong}")
    print(f"CONFIRMED      = {result.confirmed}")
    print(f"WATCH          = {result.watch}")
    print(f"REJECT         = {result.reject}")
    print(f"report         = {report}")
    print("=" * 76)
    return result


def main():
    parser = argparse.ArgumentParser(description="Deterministic MaterialScorer V1.1")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(Path(args.db), Path(args.output), rebuild=args.rebuild, limit=args.limit)


if __name__ == "__main__":
    main()
