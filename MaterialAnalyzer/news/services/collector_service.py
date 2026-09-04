from __future__ import annotations

from datetime import datetime, timezone

from ..models import CollectionResult
from ..processing.normalization import normalize_url, sha256_text


class CollectorService:
    IMMUTABLE_SOURCES = {"DART", "KIND"}
    DEFAULT_MUTABLE_REFETCH_COUNT = 3

    def __init__(
        self,
        collector,
        repository,
        normalizer,
        duplicate_checker,
        validator,
        classifier,
        source_state_repository=None,
    ):
        self.collector = collector
        self.repository = repository
        self.normalizer = normalizer
        self.duplicate_checker = duplicate_checker
        self.validator = validator
        self.classifier = classifier
        self.source_state_repository = source_state_repository

    def _refetch_recent_count(self) -> int:
        endpoint = self.collector.endpoint
        configured = endpoint.extra.get("refetch_recent_count") if getattr(endpoint, "extra", None) else None
        if configured not in (None, ""):
            try:
                return max(0, int(configured))
            except (TypeError, ValueError):
                pass
        if endpoint.source_id in self.IMMUTABLE_SOURCES:
            return 0
        if endpoint.source_type in {"GOV", "OFFICIAL"}:
            return self.DEFAULT_MUTABLE_REFETCH_COUNT
        return 0

    def _candidate_url_hash(self, candidate) -> str | None:
        canonical = normalize_url(candidate.url, candidate.source_id)
        return sha256_text(canonical or candidate.url)

    def _finish(self, result: CollectionResult) -> CollectionResult:
        result.finished_at = result.finished_at or datetime.now(timezone.utc)
        if self.source_state_repository is not None and result.run_id:
            health, failures = self.source_state_repository.finish_run(result)
            result.health_status = health
            result.consecutive_failures = failures
        elif result.failed == 0:
            result.health_status = "HEALTHY"
        else:
            result.health_status = "DEGRADED"
        return result

    def run(self) -> CollectionResult:
        endpoint = self.collector.endpoint
        started_at = datetime.now(timezone.utc)
        result = CollectionResult(
            source_id=endpoint.source_id,
            endpoint_id=endpoint.endpoint_id,
            started_at=started_at,
        )
        if self.source_state_repository is not None:
            result.run_id = self.source_state_repository.begin_run(
                endpoint.source_id,
                endpoint.endpoint_id,
                started_at,
            )

        try:
            candidates = self.collector.discover()
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"DISCOVER_FAILED: {exc}")
            return self._finish(result)

        result.discovered = len(candidates)
        if candidates:
            result.checkpoint_value = candidates[0].external_id or candidates[0].url

        refetch_recent_count = self._refetch_recent_count()

        for index, candidate in enumerate(candidates):
            try:
                known = self.repository.exists_candidate(
                    candidate,
                    url_hash=self._candidate_url_hash(candidate),
                )
                if known and index >= refetch_recent_count:
                    result.skipped += 1
                    continue

                fetched = self.collector.fetch(candidate)
                result.fetched += 1
                article = self.collector.parse(candidate, fetched)
                article.external_id = (
                    candidate.external_id
                    or article.external_id
                    or article.source_metadata.get("external_id")
                    or None
                )
                article = self.normalizer.normalize(article)
                article.article_class = self.classifier.classify(article)

                valid, error_code = self.validator.validate(article)
                if not valid:
                    result.failed += 1
                    result.errors.append(f"{candidate.url}: {error_code or 'VALIDATION_FAILED'}")
                    continue

                duplicate = self.duplicate_checker.find_exact(article)
                if duplicate and duplicate.article_id != article.article_id:
                    if duplicate.match_type == "URL" and duplicate.source_id == article.source_id:
                        article.article_id = duplicate.article_id
                        result.duplicated += 1
                    else:
                        article.duplicate_of = duplicate.article_id
                        result.duplicated += 1

                action = self.repository.upsert(article)
                if action == "INSERTED":
                    result.inserted += 1
                else:
                    result.updated += 1
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"{candidate.url}: {type(exc).__name__}: {exc}")

        return self._finish(result)
