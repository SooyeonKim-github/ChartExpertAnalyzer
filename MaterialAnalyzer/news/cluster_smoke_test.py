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


def main():
    first = datetime(2026, 9, 4, 10, 0, tzinfo=KST)
    normalizer = ArticleNormalizer()

    with tempfile.TemporaryDirectory() as td:
        database = Database(Path(td) / "cluster.db")
        article_repo = ArticleRepository(database)

        receipt = "20260904001234"
        dart = normalizer.normalize(
            _article(
                f"DART_{receipt}",
                "DART",
                receipt,
                "단일판매ㆍ공급계약체결",
                first,
                metadata={"corp_name": "삼성전자", "stock_code": "005930"},
            )
        )
        kind = normalizer.normalize(
            _article(
                f"KIND_{receipt}",
                "KIND",
                receipt,
                "단일판매·공급계약체결",
                first + timedelta(minutes=1),
                author="삼성전자",
                metadata={"company_name": "삼성전자"},
            )
        )
        other_receipt = "20260904009999"
        other = normalizer.normalize(
            _article(
                f"DART_{other_receipt}",
                "DART",
                other_receipt,
                "단일판매ㆍ공급계약체결",
                first + timedelta(minutes=2),
                metadata={"corp_name": "삼성전자", "stock_code": "005930"},
            )
        )

        for article in (dart, kind, other):
            article_repo.upsert(article)

        extractor = FeatureExtractor()
        cluster_repo = ClusterRepository(database, extractor)
        result = ArticleClusterer(cluster_repo, extractor).run()

        assert result.processed == 3
        assert result.total_clusters == 2
        assert result.multi_member_clusters == 1
        assert result.matched == 1

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

    print("[OK] ArticleCluster V1 smoke test")
    print("     DART/KIND same receipt -> one cluster")
    print("     same-source different receipt -> separate cluster")
    print("     conflicting numeric event -> no auto merge")
    print("     semantic similarity / embedding -> DISABLED")


if __name__ == "__main__":
    main()
