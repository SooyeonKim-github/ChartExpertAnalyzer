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
            _article(
                "DART_CLINICAL", "DART", "20260904009901",
                "임상시험계획 변경승인 신청", first + timedelta(minutes=3),
                metadata={"corp_name": "테스트바이오", "stock_code": "123456"},
            ),
            _article(
                "MSIT_NOISE", "MSIT", "noise-1",
                "과학기술정보통신부 인사(과장급 전보)", first + timedelta(minutes=4),
                source_type="GOV",
                body="담당 부서는 AI 지원금과 제재 관련 업무도 수행한다. 문의 043-719-4904.",
            ),
            _article(
                "KIND_WARNING", "KIND", "20260904009902",
                "투자주의종목 지정", first + timedelta(minutes=5),
                author="테스트증권", metadata={"company_name": "테스트증권"},
            ),
            _article(
                "KIND_RESUME", "KIND", "20260904009903",
                "주권매매거래정지해제", first + timedelta(minutes=6),
                author="테스트산업", metadata={"company_name": "테스트산업"},
            ),
        ]
        for article in articles:
            article_repo.upsert(normalizer.normalize(article))

        feature_extractor = FeatureExtractor()
        cluster_repo = ClusterRepository(database, feature_extractor)
        cluster_result = ArticleClusterer(cluster_repo, feature_extractor).run()
        assert cluster_result.total_clusters == 6

        event_repo = EventRepository(database)
        result = EventExtractor(event_repo, feature_extractor).run()
        assert result.processed == 6
        assert result.inserted == 6
        assert result.total_events == 6

        # sqlite3.Connection.__exit__ commits/rolls back but does not close the connection.
        # Close explicitly so Windows can remove event.db at TemporaryDirectory cleanup.
        conn = database.connect()
        try:
            rows = conn.execute(
                "SELECT event_type, event_stage, positive_negative, quantified, material_candidate, "
                "classification_source, event_title, numbers_json, stock_codes_json "
                "FROM material_events ORDER BY event_type"
            ).fetchall()
        finally:
            conn.close()

        by_title = {row["event_title"]: row for row in rows}

        order = by_title["단일판매ㆍ공급계약체결"]
        assert order["event_type"] == "ORDER_CONTRACT"
        assert order["event_stage"] == "CONFIRMED"
        assert int(order["material_candidate"]) == 1
        assert "005930" in (order["stock_codes_json"] or "")

        policy = by_title["2031년까지 해상풍력 25GW 보급 계획 발표"]
        assert policy["event_type"] == "GOV_POLICY"
        assert policy["event_stage"] == "PLANNED"
        assert int(policy["quantified"]) == 1
        assert "25GW" in (policy["numbers_json"] or "")
        assert "2031년" not in (policy["numbers_json"] or "")

        clinical = by_title["임상시험계획 변경승인 신청"]
        assert clinical["event_type"] == "CLINICAL"
        assert clinical["event_stage"] == "REQUESTED"
        assert clinical["positive_negative"] == "NEUTRAL"
        assert int(clinical["material_candidate"]) == 0

        noise = by_title["과학기술정보통신부 인사(과장급 전보)"]
        assert noise["event_type"] == "UNKNOWN"
        assert noise["classification_source"] == "NONE"
        assert int(noise["quantified"]) == 0
        assert int(noise["material_candidate"]) == 0

        warning = by_title["투자주의종목 지정"]
        assert warning["event_type"] == "MARKET_WARNING"
        assert int(warning["material_candidate"]) == 0

        resume = by_title["주권매매거래정지해제"]
        assert resume["event_type"] == "TRADING_RESUME"
        assert resume["event_stage"] == "RELEASED"
        assert resume["positive_negative"] == "NEUTRAL"

        repeat = EventExtractor(event_repo, feature_extractor).run()
        assert repeat.processed == 0

        report = event_repo.export_report(Path(td) / "event_report.csv")
        assert report.exists()

    print("[OK] EventExtractor V1.1 smoke test")
    print("     title-first classification -> OK")
    print("     body AI/subsidy noise -> UNKNOWN, not material")
    print("     approval application -> REQUESTED / NEUTRAL")
    print("     trading halt release -> RELEASED / NEUTRAL")
    print("     administrative warning -> material_candidate=0")
    print("     meaningful number 25GW -> quantified; calendar year/phone -> ignored")
    print("     incremental repeat -> processed=0")
    print("     event_report.csv -> OK")
    print("     windows sqlite cleanup -> OK")


if __name__ == "__main__":
    main()
