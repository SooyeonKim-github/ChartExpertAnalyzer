from __future__ import annotations

import argparse
from pathlib import Path

from .collectors import CollectorFactory
from .config_loader import load_endpoints
from .processing import ArticleNormalizer, ArticleValidator, ExactDuplicateChecker, RuleArticleClassifier
from .services import CollectorService
from .storage import ArticleRepository, Database, SourceStateRepository


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"


def run(db_path: Path = DEFAULT_DB):
    database = Database(db_path)
    repository = ArticleRepository(database)
    source_state_repository = SourceStateRepository(database)
    normalizer = ArticleNormalizer()
    duplicate_checker = ExactDuplicateChecker(repository)
    validator = ArticleValidator()
    classifier = RuleArticleClassifier()
    endpoints = load_endpoints(only_enabled=True)

    print("=" * 72)
    print(" NewsCollector V1.5 - Incremental + Source Health")
    print("=" * 72)
    print(f"DB        : {db_path}")
    print(f"Endpoints : {len(endpoints)}")
    print("-" * 72)

    totals = {
        "discovered": 0,
        "fetched": 0,
        "inserted": 0,
        "updated": 0,
        "duplicated": 0,
        "skipped": 0,
        "failed": 0,
    }

    for endpoint in endpoints:
        try:
            collector = CollectorFactory.create(endpoint)
            service = CollectorService(
                collector,
                repository,
                normalizer,
                duplicate_checker,
                validator,
                classifier,
                source_state_repository=source_state_repository,
            )
            result = service.run()
        except Exception as exc:
            print(f"[FAIL] {endpoint.endpoint_id:<22} {type(exc).__name__}: {exc}")
            totals["failed"] += 1
            continue

        for key in totals:
            totals[key] += getattr(result, key)

        status = "OK" if result.failed == 0 else "WARN"
        print(
            f"[{status:<4}] {endpoint.endpoint_id:<22} "
            f"found={result.discovered:<4} fetch={result.fetched:<4} "
            f"new={result.inserted:<4} upd={result.updated:<4} "
            f"skip={result.skipped:<4} dup={result.duplicated:<3} fail={result.failed:<3} "
            f"health={result.health_status}"
        )
        if result.consecutive_failures:
            print(f"       consecutive_failures={result.consecutive_failures}")
        for error in result.errors[:3]:
            print(f"       - {error}")

    print("-" * 72)
    print("TOTAL " + " ".join(f"{key}={value}" for key, value in totals.items()))
    print("=" * 72)
    return totals


def main():
    parser = argparse.ArgumentParser(description="MaterialAnalyzer NewsCollector V1.5")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    run(Path(args.db))


if __name__ == "__main__":
    main()
