from __future__ import annotations

import argparse
from pathlib import Path

from .clustering import ArticleClusterer, FeatureExtractor
from .storage import ClusterRepository, Database


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"
DEFAULT_REPORT = ROOT / "data" / "cluster_report.csv"


def run(
    db_path: Path = DEFAULT_DB,
    output_path: Path = DEFAULT_REPORT,
    *,
    rebuild: bool = False,
    limit: int | None = None,
):
    database = Database(db_path)
    extractor = FeatureExtractor()
    repository = ClusterRepository(database, extractor)
    clusterer = ArticleClusterer(repository, extractor)

    print("=" * 76)
    print(" ArticleCluster V1 - Rule Based Only")
    print(" Semantic Similarity / Embedding: DISABLED")
    print("=" * 76)
    print(f"DB      : {db_path}")
    print(f"Report  : {output_path}")
    print(f"Mode    : {'REBUILD' if rebuild else 'INCREMENTAL'}")
    print("-" * 76)

    result = clusterer.run(rebuild=rebuild, limit=limit)
    report = repository.export_report(output_path)

    singleton = result.total_clusters - result.multi_member_clusters
    print(f"processed             = {result.processed}")
    print(f"matched_existing      = {result.matched}")
    print(f"created_new_clusters  = {result.created}")
    print(f"total_clusters        = {result.total_clusters}")
    print(f"multi_member_clusters = {result.multi_member_clusters}")
    print(f"singleton_clusters    = {singleton}")
    print(f"report                = {report}")
    print("=" * 76)
    return result


def main():
    parser = argparse.ArgumentParser(description="Rule-only ArticleCluster V1")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(Path(args.db), Path(args.output), rebuild=args.rebuild, limit=args.limit)


if __name__ == "__main__":
    main()
