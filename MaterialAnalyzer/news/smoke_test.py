from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from .collectors import CollectorFactory
from .config_loader import load_endpoints, load_sources
from .models import ArticleCandidate, RawArticle
from .processing import ArticleNormalizer, ArticleValidator, ExactDuplicateChecker, RuleArticleClassifier
from .services import CollectorService
from .storage import ArticleRepository, Database, SourceStateRepository


KST = timezone(timedelta(hours=9))
EXPECTED_LIVE_ENDPOINTS = {
    "DART_DISCLOSURE",
    "KIND_TODAY",
    "MOTIR_PRESS",
    "MSIT_PRESS",
    "MCEE_PRESS",
    "MFDS_PRESS",
    "FSC_PRESS",
}


def _sample(
    collected_at: datetime,
    *,
    body: str | None = "본문입니다.\n\nCopyright 2026 Test\n계약 규모 1조원",
    source_id: str = "TEST",
    endpoint_id: str = "TEST_NEWS",
    article_id: str = "TEST_001",
    external_id: str | None = None,
    url: str = "https://example.com/news/1?utm_source=naver&article_id=1#top",
) -> RawArticle:
    return RawArticle(
        article_id=article_id,
        source_id=source_id,
        endpoint_id=endpoint_id,
        source_name="Test News",
        source_type="NEWS",
        source_grade="A",
        title="[특징주]   삼성전자, HBM4 공급 본격화",
        body=body,
        summary=None,
        url=url,
        canonical_url=None,
        author=None,
        published_at=collected_at,
        updated_at=None,
        collected_at=collected_at,
        published_date=None,
        market_date=None,
        category="STOCK",
        language="ko",
        article_class="UNKNOWN",
        collector_type="HTML_LIST",
        content_mode="DISCOVERY",
        external_id=external_id,
    )


class _FakeDartCollector:
    def __init__(self, candidate: ArticleCandidate):
        self.candidate = candidate
        self.endpoint = SimpleNamespace(
            source_id="DART",
            endpoint_id="DART_TEST",
            source_type="OFFICIAL",
            extra={},
        )

    def discover(self):
        return [self.candidate]

    def fetch(self, candidate):
        raise AssertionError("known immutable candidate must be skipped before fetch")

    def parse(self, candidate, fetched):
        raise AssertionError("known immutable candidate must not be parsed")


def main():
    sources = load_sources()
    endpoints = load_endpoints(only_enabled=False)
    live_endpoints = load_endpoints(only_enabled=True)
    assert len(sources) == 36, f"expected 36 sources, got {len(sources)}"
    assert len(endpoints) == 36, f"expected 36 endpoints, got {len(endpoints)}"
    assert {item.endpoint_id for item in live_endpoints} == EXPECTED_LIVE_ENDPOINTS
    assert "DART_API" in CollectorFactory.REGISTRY
    assert "KIND_HTML" in CollectorFactory.REGISTRY
    assert "GOV_HTML_LIST" in CollectorFactory.REGISTRY
    assert "NEWS_SECTION" in CollectorFactory.REGISTRY

    normalizer = ArticleNormalizer()
    first = datetime(2026, 9, 4, 16, 0, tzinfo=KST)
    second = datetime(2026, 9, 4, 16, 5, tzinfo=KST)

    article = normalizer.normalize(_sample(first))
    assert article.canonical_url == "https://example.com/news/1?article_id=1"
    assert article.title.startswith("[특징주]")
    assert "Copyright" not in (article.body or "")
    assert article.market_date == "20260907"
    assert article.url_hash and article.title_hash and article.content_hash
    assert article.first_seen_at == first and article.last_seen_at == first

    bodyless = normalizer.normalize(_sample(first, body=None))
    assert bodyless.title_hash
    assert bodyless.content_hash is None

    with tempfile.TemporaryDirectory() as td:
        database = Database(Path(td) / "news.db")
        repo = ArticleRepository(database)
        state_repo = SourceStateRepository(database)
        assert repo.exists_article_id("missing") is False
        assert repo.upsert(article) == "INSERTED"

        duplicate_checker = ExactDuplicateChecker(repo)
        reobserved = normalizer.normalize(_sample(second))
        match = duplicate_checker.find_exact(reobserved)
        assert match and match.match_type == "URL" and match.article_id == article.article_id
        assert repo.upsert(reobserved) == "UPDATED"

        saved = repo.get_by_article_id(article.article_id)
        assert saved is not None
        assert saved["first_seen_at"] == first.isoformat()
        assert saved["last_seen_at"] == second.isoformat()
        assert saved["published_at_precision"] == "SECOND"

        dart_url = "https://example.com/dart/EXT001"
        dart_article = normalizer.normalize(
            _sample(
                first,
                source_id="DART",
                endpoint_id="DART_TEST",
                article_id="DART_EXT001",
                external_id="EXT001",
                url=dart_url,
                body=None,
            )
        )
        assert repo.upsert(dart_article) == "INSERTED"
        candidate = ArticleCandidate(
            source_id="DART",
            endpoint_id="DART_TEST",
            url=dart_url,
            external_id="EXT001",
            title_hint="테스트 공시",
        )
        service = CollectorService(
            _FakeDartCollector(candidate),
            repo,
            normalizer,
            ExactDuplicateChecker(repo),
            ArticleValidator(),
            RuleArticleClassifier(),
            source_state_repository=state_repo,
        )
        incremental_result = service.run()
        assert incremental_result.discovered == 1
        assert incremental_result.fetched == 0
        assert incremental_result.skipped == 1
        assert incremental_result.failed == 0
        assert incremental_result.health_status == "HEALTHY"
        state = state_repo.get_state("DART", "DART_TEST")
        assert state is not None
        assert state["health_status"] == "HEALTHY"
        assert state["last_skipped_count"] == 1
        assert state["last_fetched_count"] == 0

    print("[OK] NewsCollector V1.5 smoke test")
    print(f"     sources={len(sources)} endpoints={len(endpoints)} live={len(live_endpoints)}")
    print("     live endpoints=" + ", ".join(sorted(EXPECTED_LIVE_ENDPOINTS)))
    print("     normalizer=OK first_seen/last_seen=OK market_date=20260907")
    print("     exact-dedupe=OK bodyless-content-hash=NONE")
    print("     incremental=OK known-DART fetch=0 skip=1")
    print("     source-health=OK HEALTHY run-history=OK")


if __name__ == "__main__":
    main()
