from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .collectors import CollectorFactory
from .config_loader import load_endpoints, load_sources
from .models import RawArticle
from .processing import ArticleNormalizer, ExactDuplicateChecker
from .storage import ArticleRepository, Database


KST = timezone(timedelta(hours=9))


def _sample(collected_at: datetime) -> RawArticle:
    return RawArticle(
        article_id="TEST_001",
        source_id="TEST",
        endpoint_id="TEST_NEWS",
        source_name="Test News",
        source_type="NEWS",
        source_grade="A",
        title="[특징주]   삼성전자, HBM4 공급 본격화",
        body="본문입니다.\n\nCopyright 2026 Test\n계약 규모 1조원",
        summary=None,
        url="https://example.com/news/1?utm_source=naver&article_id=1#top",
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
    )


def main():
    sources = load_sources()
    endpoints = load_endpoints(only_enabled=False)
    assert len(sources) == 36, f"expected 36 sources, got {len(sources)}"
    assert len(endpoints) == 36, f"expected 36 endpoints, got {len(endpoints)}"
    assert "DART_API" in CollectorFactory.REGISTRY
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

    with tempfile.TemporaryDirectory() as td:
        repo = ArticleRepository(Database(Path(td) / "news.db"))
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

    print("[OK] NewsCollector V1.1 smoke test")
    print(f"     sources={len(sources)} endpoints={len(endpoints)}")
    print("     normalizer=OK first_seen/last_seen=OK market_date=20260907")


if __name__ == "__main__":
    main()
