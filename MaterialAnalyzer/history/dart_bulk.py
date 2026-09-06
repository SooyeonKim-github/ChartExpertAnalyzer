from __future__ import annotations

from datetime import datetime, timezone

from MaterialAnalyzer.news.models import CollectionResult

from .dart_prefilter import classify_dart_analysis


class HistoricalDartBulkService:
    """Fast path for immutable OpenDART list metadata.

    DART historical fetch() does not download a detail body; it wraps immutable list
    metadata. We therefore batch external-id existence checks and commit all new rows
    in one SQLite transaction instead of doing multiple DB round-trips per disclosure.
    """

    def __init__(self, collector, repository, normalizer, validator, classifier):
        self.collector = collector
        self.repository = repository
        self.normalizer = normalizer
        self.validator = validator
        self.classifier = classifier

    def run(self) -> CollectionResult:
        endpoint = self.collector.endpoint
        result = CollectionResult(
            source_id=endpoint.source_id,
            endpoint_id=endpoint.endpoint_id,
            started_at=datetime.now(timezone.utc),
        )
        try:
            discovered = self.collector.discover()
        except Exception as exc:
            result.failed = 1
            result.errors.append(f"DISCOVER_FAILED: {type(exc).__name__}: {exc}")
            result.finished_at = datetime.now(timezone.utc)
            result.health_status = "DEGRADED"
            return result

        # Deduplicate within the API response before touching SQLite.
        candidates = []
        seen = set()
        for candidate in discovered:
            key = candidate.external_id or candidate.url
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
        result.discovered = len(candidates)
        if candidates:
            result.checkpoint_value = candidates[-1].external_id or candidates[-1].url

        known = self.repository.existing_external_ids(
            endpoint.source_id,
            [candidate.external_id for candidate in candidates if candidate.external_id],
        )
        result.skipped = sum(1 for candidate in candidates if candidate.external_id in known)

        articles = []
        for candidate in candidates:
            if candidate.external_id in known:
                continue
            try:
                fetched = self.collector.fetch(candidate)
                result.fetched += 1
                article = self.collector.parse(candidate, fetched)
                article.external_id = candidate.external_id or article.external_id
                article = self.normalizer.normalize(article)
                article.article_class = self.classifier.classify(article)
                stock_code = str(candidate.metadata.get("stock_code", "") or "").strip()
                article.analysis_status = classify_dart_analysis(article.title, stock_code)
                valid, error_code = self.validator.validate(article)
                if not valid:
                    result.failed += 1
                    result.errors.append(
                        f"{candidate.external_id or candidate.url}: {error_code or 'VALIDATION_FAILED'}"
                    )
                    continue
                articles.append(article)
            except Exception as exc:
                result.failed += 1
                result.errors.append(
                    f"{candidate.external_id or candidate.url}: {type(exc).__name__}: {exc}"
                )

        inserted, updated = self.repository.upsert_many(articles)
        result.inserted = inserted
        result.updated = updated
        result.finished_at = datetime.now(timezone.utc)
        result.health_status = "HEALTHY" if result.failed == 0 else "DEGRADED"
        return result
