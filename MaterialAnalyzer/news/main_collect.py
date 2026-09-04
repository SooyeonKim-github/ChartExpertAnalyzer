from __future__ import annotations

import argparse
from pathlib import Path

from .collectors import CollectorFactory
from .config_loader import load_endpoints
from .processing import ArticleNormalizer, ArticleValidator, ExactDuplicateChecker, RuleArticleClassifier
from .services import CollectorService
from .storage import ArticleRepository, Database


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"


def run(db_path: Path = DEFAULT_DB):
    database = Database(db_path)
    repository = ArticleRepository(database)
    normalizer = ArticleNormalizer()
    duplicate_checker = ExactDuplicateChecker(repository)
    validator = ArticleValidator()
    classifier = RuleArticleClassifier()
    endpoints = load_endpoints(only_enabled=True)
    print("=" * 58)
    print(" NewsCollector V1.1")
    print("=" * 58)
    print(f"DB        : {db_path}")
    print(f"Endpoints : {len(endpoints)}")
    print("-" * 58)
    totals = {"discovered":0,"fetched":0,"inserted":0,"updated":0,"duplicated":0,"skipped":0,"failed":0}
    for endpoint in endpoints:
        try:
            collector = CollectorFactory.create(endpoint)
            service = CollectorService(collector, repository, normalizer, duplicate_checker, validator, classifier)
            result = service.run()
        except Exception as exc:
            print(f"[FAIL] {endpoint.endpoint_id:<24} {type(exc).__name__}: {exc}")
            totals["failed"] += 1
            continue
        for key in totals:
            totals[key] += getattr(result, key)
        status = "OK" if result.failed == 0 else "WARN"
        print(f"[{status:<4}] {endpoint.endpoint_id:<24} new={result.inserted:<4} upd={result.updated:<4} dup={result.duplicated:<4} fail={result.failed:<3}")
        for error in result.errors[:3]:
            print(f"       - {error}")
    print("-" * 58)
    print("TOTAL " + " ".join(f"{key}={value}" for key, value in totals.items()))
    print("=" * 58)
    return totals


def main():
    parser = argparse.ArgumentParser(description="MaterialAnalyzer NewsCollector V1.1")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    run(Path(args.db))


if __name__ == "__main__":
    main()
