from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .clustering import ArticleClusterer, FeatureExtractor
from .events import EventExtractor
from .models import RawArticle
from .processing import ArticleNormalizer
from .storage import ArticleRepository, ClusterRepository, Database, EventRepository


KST = timezone(timedelta(hours=9))


def _article(
    article_id: str,
    source_id: str,
    external_id: str,
    title: str,
    seen_at: datetime,
    *,
    source_type: str = "OFFICIAL",
    source_grade: str = "S",
    author: str | None = None,
    body: str | None = None,
    metadata: dict | None = None,
) -> RawArticle:
    return RawArticle(
        article_id=article_id,
        source_id=source_id,
        endpoint_id=f"{source_id}_TEST",
        source_name=source_id,
        source_type=source_type,
        source_grade=source_grade,
        title=title,
        body=body,
        summary=None,
        url=f"https://example.com/{source_id}/{external_id}",
        canonical_url=None,
        author=author,
        published_at=seen_at,
        updated_at=None,
        collected_at=seen_at,
        published_date=None,
        market_date=None,
        category="DISCLOSURE" if source_id in {"DART", "KIND"} else "GOV_POLICY",
        language="ko",
        article_class="DISCLOSURE" if source_id in {"DART", "KIND"} else "PRESS_RELEASE",
        collector_type="TEST",
        content_mode="FULL",
        external_id=external_id,
        source_metadata=metadata or {},
    )


def main():
    first = datetime(2026, 9, 4, 10, 0, tzinfo=KST)
    normalizer = ArticleNormalizer()

    with tempfile.TemporaryDirectory() as td:
        database = Database(Path(td) / "event.db")
        article_repo = ArticleRepository(database)

        receipt = "20260904001234"
        articles = [
            _article(
                f"DART_{receipt}", "DART", receipt,
                "단일판매ㆍ공급계약체결", first,
                metadata={"corp_name": "삼성전자", "stock_code": "005930"},
            ),
            _article(
                f"KIND_{receipt}", "KIND", receipt,
                "단일판매·공급계약체결", first + timedelta(minutes=1),
                author="삼성전자", metadata={"company_name": "삼성전자"},
            ),
            _article(
                "MOTIR_POLICY", "MOTIR", "policy-1",
                "2031년까지 해상풍력 25GW 보급 계획 발표", first + timedelta(minutes=2),
                source_type="GOV", body="정부는 해상풍력 보급 확대를 위한 기본계획을 발표했다.",
            ),
        ]
        for article in articles:
            article_repo.upsert(normalizer.normalize(article))

        feature_extractor = FeatureExtractor()
        cluster_repo = ClusterRepository(database, feature_extractor)
        cluster_result = ArticleClusterer(cluster_repo, feature_extractor).run()
        assert cluster_result.total_clusters == 2

        event_repo = EventRepository(database)
        result = EventExtractor(event_repo, feature_extractor).run()
        assert result.processed == 2
        assert result.inserted == 2
        assert result.total_events == 2

        # sqlite3.Connection.__exit__ commits/rolls back but does not close the
        # connection. On Windows that leaves event.db locked until the local
        # variable is destroyed, so close explicitly before TemporaryDirectory
        # attempts to delete the database file.
        conn = database.connect()
        try:
            rows = conn.execute(
                "SELECT event_type, event_stage, positive_negative, quantified, stock_codes_json "
                "FROM material_events ORDER BY event_type"
            ).fetchall()
        finally:
            conn.close()

        types = {row["event_type"] for row in rows}
        assert "ORDER_CONTRACT" in types
        assert "GOV_POLICY" in types

        order = next(row for row in rows if row["event_type"] == "ORDER_CONTRACT")
        assert order["event_stage"] == "CONFIRMED"
        assert "005930" in (order["stock_codes_json"] or "")

        policy = next(row for row in rows if row["event_type"] == "GOV_POLICY")
        assert policy["event_stage"] == "PLANNED"
        assert int(policy["quantified"]) == 1

        repeat = EventExtractor(event_repo, feature_extractor).run()
        assert repeat.processed == 0

        report = event_repo.export_report(Path(td) / "event_report.csv")
        assert report.exists()

    print("[OK] EventExtractor V1 smoke test")
    print("     cluster -> one material_event")
    print("     DART/KIND contract -> ORDER_CONTRACT / CONFIRMED")
    print("     government 25GW plan -> GOV_POLICY / PLANNED / quantified")
    print("     incremental repeat -> processed=0")
    print("     event_report.csv -> OK")
    print("     windows sqlite cleanup -> OK")


if __name__ == "__main__":
    main()
