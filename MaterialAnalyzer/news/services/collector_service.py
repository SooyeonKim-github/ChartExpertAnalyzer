from __future__ import annotations

from datetime import datetime, timezone

from ..models import CollectionResult


class CollectorService:
    def __init__(self, collector, repository, normalizer, duplicate_checker, validator, classifier):
        self.collector = collector
        self.repository = repository
        self.normalizer = normalizer
        self.duplicate_checker = duplicate_checker
        self.validator = validator
        self.classifier = classifier

    def run(self) -> CollectionResult:
        endpoint = self.collector.endpoint
        result = CollectionResult(source_id=endpoint.source_id, endpoint_id=endpoint.endpoint_id, started_at=datetime.now(timezone.utc))
        try:
            candidates = self.collector.discover()
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"DISCOVER_FAILED: {exc}")
            result.finished_at = datetime.now(timezone.utc)
            return result
        result.discovered = len(candidates)
        for candidate in candidates:
            try:
                if self.repository.exists_candidate(candidate):
                    result.skipped += 1
                    continue
                fetched = self.collector.fetch(candidate)
                result.fetched += 1
                article = self.collector.parse(candidate, fetched)
                article = self.normalizer.normalize(article)
                article.article_class = self.classifier.classify(article)
                valid, error_code = self.validator.validate(article)
                if not valid:
                    result.failed += 1
                    result.errors.append(f"{candidate.url}: {error_code or 'VALIDATION_FAILED'}")
                    continue
                duplicate = self.duplicate_checker.find_exact(article)
                if duplicate and duplicate["article_id"] != article.article_id:
                    article.duplicate_of = duplicate["article_id"]
                    result.duplicated += 1
                action = self.repository.upsert(article)
                if action == "INSERTED":
                    result.inserted += 1
                else:
                    result.updated += 1
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"{candidate.url}: {type(exc).__name__}: {exc}")
        result.finished_at = datetime.now(timezone.utc)
        return result
