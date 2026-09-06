from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from MaterialAnalyzer.news.config_loader import load_endpoints
from MaterialAnalyzer.news.processing import ArticleValidator, ExactDuplicateChecker, RuleArticleClassifier
from MaterialAnalyzer.news.services import CollectorService
from MaterialAnalyzer.news.storage import ArticleRepository, Database

from .chunk_planner import plan_chunks
from .collectors import DartRangeCollector, GovernmentRangeCollector
from .dart_bulk import HistoricalDartBulkService
from .historical_market_date import HistoricalMarketDateResolver
from .historical_normalizer import HistoricalArticleNormalizer
from .models import HistoricalRangeConfig, RangeChunk
from .repository import HistoricalRangeRepository
from .source_capabilities import LIVE_ONLY, PAGED_LIST, RANGE_API, historical_mode


@dataclass
class HistoricalCollectionSummary:
    complete_chunks: int = 0
    skipped_chunks: int = 0
    failed_chunks: int = 0
    discovered: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


class HistoricalRangeCollector:
    def __init__(self, db_path: str | Path, config: HistoricalRangeConfig):
        self.db_path = Path(db_path)
        self.config = config
        self.config.validate()
        self.state = HistoricalRangeRepository(self.db_path)
        self.database = Database(self.db_path)
        self.article_repository = ArticleRepository(self.database)
        resolver = HistoricalMarketDateResolver(config.context_start, config.requested_end)
        self.normalizer = HistoricalArticleNormalizer(resolver)
        self.duplicate_checker = ExactDuplicateChecker(self.article_repository)
        self.validator = ArticleValidator()
        self.classifier = RuleArticleClassifier()
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT external_id FROM articles WHERE source_id='DART' AND external_id IS NOT NULL"
            ).fetchall()
        self.known_dart_ids = {str(row["external_id"]) for row in rows if row["external_id"]}
        if self.known_dart_ids:
            print(f"[FAST] cached existing DART receipt ids={len(self.known_dart_ids):,}")

    def _service(self, collector) -> CollectorService:
        return CollectorService(
            collector,
            self.article_repository,
            self.normalizer,
            self.duplicate_checker,
            self.validator,
            self.classifier,
            source_state_repository=None,
        )

    def _collect_chunk(self, endpoint, chunk: RangeChunk):
        mode = historical_mode(endpoint.source_id)
        if mode == RANGE_API:
            collector = DartRangeCollector(endpoint, chunk.start, chunk.end)
            return HistoricalDartBulkService(
                collector,
                self.article_repository,
                self.normalizer,
                self.validator,
                self.classifier,
                known_external_ids=self.known_dart_ids,
            ).run()
        if mode == PAGED_LIST:
            collector = GovernmentRangeCollector(
                endpoint,
                chunk.start,
                chunk.end,
                max_pages=self.config.government_max_pages,
            )
            return self._service(collector).run()
        raise RuntimeError(f"historical collection unsupported: {endpoint.source_id} mode={mode}")

    @staticmethod
    def _add(summary: HistoricalCollectionSummary, result) -> None:
        summary.discovered += int(result.discovered or 0)
        summary.inserted += int(result.inserted or 0)
        summary.updated += int(result.updated or 0)
        summary.skipped += int(result.skipped or 0)
        summary.failed += int(result.failed or 0)

    def run(self) -> HistoricalCollectionSummary:
        endpoints = load_endpoints(only_enabled=True)
        summary = HistoricalCollectionSummary()
        print("\n[Historical Collection]")

        for endpoint in endpoints:
            mode = historical_mode(endpoint.source_id)
            if mode == LIVE_ONLY:
                print(f"[SKIP] {endpoint.endpoint_id:<22} historical_mode=LIVE_ONLY")
                self.state.mark_coverage_range(
                    endpoint.source_id,
                    self.config.context_start,
                    self.config.requested_end,
                    status="LIVE_ONLY",
                    note="historical collector intentionally disabled",
                )
                continue
            if mode not in {RANGE_API, PAGED_LIST}:
                continue

            if mode == RANGE_API:
                chunks = plan_chunks(
                    endpoint.source_id,
                    self.config.context_start,
                    self.config.requested_end,
                    self.config.chunk_days,
                )
            else:
                chunks = [RangeChunk(endpoint.source_id, self.config.context_start, self.config.requested_end)]

            print(f"\n{endpoint.endpoint_id} mode={mode} chunks={len(chunks)}")
            for index, chunk in enumerate(chunks, start=1):
                if self.state.is_complete(chunk):
                    summary.skipped_chunks += 1
                    if index == 1 or index == len(chunks) or index % 25 == 0:
                        print(f"  [{index:>4}/{len(chunks)}] {chunk.start}~{chunk.end} SKIP complete")
                    continue

                self.state.mark_running(chunk)
                try:
                    result = self._collect_chunk(endpoint, chunk)
                    errors = list(getattr(result, "errors", []) or [])
                    if result.failed and not result.discovered and errors:
                        raise RuntimeError(" | ".join(errors[:3]))
                    self.state.mark_result(chunk, result)
                    self._add(summary, result)
                    summary.complete_chunks += 1
                    print(
                        f"  [{index:>4}/{len(chunks)}] {chunk.start}~{chunk.end} "
                        f"found={result.discovered} new={result.inserted} upd={result.updated} "
                        f"skip={result.skipped} fail={result.failed}"
                    )
                except Exception as exc:
                    summary.failed_chunks += 1
                    summary.failed += 1
                    self.state.mark_result(chunk, None, error=f"{type(exc).__name__}: {exc}")
                    print(f"  [{index:>4}/{len(chunks)}] {chunk.start}~{chunk.end} FAILED {type(exc).__name__}: {exc}")
                    if not self.config.continue_on_error:
                        raise
        return summary
