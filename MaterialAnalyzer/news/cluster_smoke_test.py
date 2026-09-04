from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .clustering import ArticleClusterer, ArticleFeatures, FeatureExtractor, PairScorer
from .models import RawArticle
from .processing import ArticleNormalizer
from .storage import ArticleRepository, ClusterRepository, Database


KST = timezone(timedelta(hours=9))


def _article(
    article_id: str,
    source_id: str,
    external_id: str,
    title: str,
    seen_at: datetime,
    *,
    author: str | None = None,
    metadata: dict | None = None,
) -> RawArticle:
    return RawArticle(
        article_id=article_id,
        source_id=source_id,
        endpoint_id=f"{source_id}_TEST",
        source_name=source_id,
        source_type="OFFICIAL",
        source_grade="S",
        title=title,
        body=None,
        summary=None,
        url=f"https://example.com/{source_id}/{external_id}",
        canonical_url=None,
        author=author,
        published_at=seen_at,
        updated_at=None,
        collected_at=seen_at,
        published_date=None,
        market_date=None,
        category="DISCLOSURE",
        language="ko",
        article_class="DISCLOSURE",
        collector_type="TEST",
        content_mode="DISCOVERY",
        external_id=external_id,
        source_metadata=metadata or {},
    )


def _save(repo, normalizer, *articles):
    for article in articles:
        repo.upsert(normalizer.normalize(article))


def main():
    first = datetime(2026, 9, 4, 10, 0, tzinfo=KST)
    normalizer = ArticleNormalizer()

    with tempfile.TemporaryDirectory() as td:
        database = Database(Path(td) / "cluster.db")
        article_repo = ArticleRepository(database)
        receipt = "20260904001234"
        _save(
            article_repo,
            normalizer,
            _article(
                f"DART_{receipt}", "DART", receipt, "단일판매ㆍ공급계약체결", first,
                metadata={"corp_name": "삼성전자", "stock_code": "005930"},
            ),
            _article(
                f"KIND_{receipt}", "KIND", receipt, "단일판매·공급계약체결",
                first + timedelta(minutes=1), author="삼성전자",
                metadata={"company_name": "삼성전자"},
            ),
            _article(
                "DART_20260904009999", "DART", "20260904009999",
                "단일판매ㆍ공급계약체결", first + timedelta(minutes=2),
                metadata={"corp_name": "삼성전자", "stock_code": "005930"},
            ),
        )
        extractor = FeatureExtractor()
        result = ArticleClusterer(ClusterRepository(database, extractor), extractor).run()
        assert result.processed == 3
        assert result.total_clusters == 2
        assert result.multi_member_clusters == 1
        assert result.matched == 1

    with tempfile.TemporaryDirectory() as td:
        database = Database(Path(td) / "ambiguous.db")
        article_repo = ArticleRepository(database)
        title = "임원ㆍ주요주주특정증권등소유상황보고서"
        _save(
            article_repo,
            normalizer,
            _article("DART_A", "DART", "20260904900536", title, first,
                     metadata={"corp_name": "제테마", "stock_code": "216080"}),
            _article("DART_B", "DART", "20260904900539", title, first + timedelta(minutes=1),
                     metadata={"corp_name": "제테마", "stock_code": "216080"}),
            _article("KIND_A", "KIND", "20260904000752", title, first + timedelta(minutes=2),
                     author="제테마", metadata={"company_name": "제테마"}),
            _article("KIND_B", "KIND", "20260904000746", title, first + timedelta(minutes=3),
                     author="제테마", metadata={"company_name": "제테마"}),
        )
        extractor = FeatureExtractor()
        result = ArticleClusterer(ClusterRepository(database, extractor), extractor).run()
        assert result.total_clusters == 4
        assert result.ambiguity_blocked >= 1

    with tempfile.TemporaryDirectory() as td:
        database = Database(Path(td) / "bridge.db")
        article_repo = ArticleRepository(database)
        title = "임원ㆍ주요주주특정증권등소유상황보고서"
        _save(
            article_repo,
            normalizer,
            _article("DART_A", "DART", "20260904900752", title, first,
                     metadata={"corp_name": "제테마", "stock_code": "216080"}),
            _article("DART_B", "DART", "20260904900746", title, first + timedelta(minutes=1),
                     metadata={"corp_name": "제테마", "stock_code": "216080"}),
            _article("KIND_A", "KIND", "20260904000752", title, first + timedelta(minutes=2),
                     author="제테마", metadata={"company_name": "제테마"}),
            _article("KIND_B", "KIND", "20260904000746", title, first + timedelta(minutes=3),
                     author="제테마", metadata={"company_name": "제테마"}),
        )
        extractor = FeatureExtractor()
        result = ArticleClusterer(ClusterRepository(database, extractor), extractor).run()
        assert result.total_clusters == 2
        assert result.multi_member_clusters == 2
        assert result.matched == 2

    scorer = PairScorer()
    left = ArticleFeatures(
        article_id="A", source_id="MOTIR", source_type="GOV", source_grade="S",
        article_class="PRESS_RELEASE", market_date="20260904",
        normalized_title="해상풍력 25gw 보급 계획", tokens=("해상풍력", "25gw", "보급", "계획"),
        numbers=("25gw",), event_type="POLICY",
    )
    right = ArticleFeatures(
        article_id="B", source_id="NEWS", source_type="NEWS", source_grade="A",
        article_class="ORIGINAL_NEWS", market_date="20260904",
        normalized_title="해상풍력 10gw 보급 계획", tokens=("해상풍력", "10gw", "보급", "계획"),
        numbers=("10gw",), event_type="POLICY",
    )
    assert scorer.score(left, right).score < scorer.AUTO_MATCH_THRESHOLD

    print("[OK] ArticleCluster V1.1 smoke test")
    print("     DART/KIND exact receipt -> one cluster")
    print("     DART/KIND bridge id -> strong match")
    print("     repeated same-company/title disclosure -> ambiguity guard")
    print("     same-source different receipt -> separate cluster")
    print("     conflicting numeric event -> no auto merge")
    print("     semantic similarity / embedding -> DISABLED")


if __name__ == "__main__":
    main()
