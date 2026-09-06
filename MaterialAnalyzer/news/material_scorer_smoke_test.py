from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .scoring import MaterialScorer
from .storage import Database, MaterialScoreRepository


def _insert_event(
    conn,
    *,
    event_id: str,
    market_date: str,
    source_id: str,
    source_grade: str,
    source_type: str,
    title: str,
    event_type: str,
    stage: str,
    novelty_status: str,
    novelty_score: float,
    company: str = "",
    ticker: str = "",
    numbers: tuple[str, ...] = (),
    source_count: int = 1,
    confirmation_count: int = 0,
):
    article_id = f"A_{event_id}"
    cluster_id = f"CL_{event_id}"
    family_id = f"FAM_{event_id}"
    seen_at = f"{market_date[:4]}-{market_date[4:6]}-{market_date[6:]}T09:00:00+09:00"

    conn.execute(
        "INSERT INTO articles("
        "article_id, source_id, endpoint_id, source_name, source_type, source_grade, title, url, "
        "collected_at, first_seen_at, last_seen_at, market_date, article_class"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ORIGINAL_NEWS')",
        (
            article_id,
            source_id,
            f"{source_id}_TEST",
            source_id,
            source_type,
            source_grade,
            title,
            f"https://example.com/{event_id}",
            seen_at,
            seen_at,
            seen_at,
            market_date,
        ),
    )
    conn.execute(
        "INSERT INTO material_events("
        "event_id, cluster_id, representative_article_id, event_type, event_stage, event_title, "
        "event_summary, positive_negative, quantified, material_candidate, material_candidate_reason, "
        "classification_source, companies_json, stock_codes_json, numbers_json, original_source_id, "
        "original_source_name, article_count, source_count, confirmation_count, first_seen_at, last_seen_at, "
        "market_date, extraction_confidence, extraction_version, cluster_updated_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, 'POSITIVE', ?, 1, 'MATERIAL_EVENT', 'TITLE', ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, 90, 'RULE_EVENT_V1_1', ?, ?)",
        (
            event_id,
            cluster_id,
            article_id,
            event_type,
            stage,
            title,
            title,
            int(bool(numbers)),
            json.dumps([company] if company else [], ensure_ascii=False),
            json.dumps([ticker] if ticker else [], ensure_ascii=False),
            json.dumps(list(numbers), ensure_ascii=False),
            source_id,
            source_id,
            source_count,
            confirmation_count,
            seen_at,
            seen_at,
            market_date,
            seen_at,
            seen_at,
        ),
    )
    conn.execute(
        "INSERT INTO event_novelty("
        "event_id, family_id, novelty_status, novelty_score, relation_score, analysis_version, event_updated_at, updated_at"
        ") VALUES (?, ?, ?, ?, 0, 'RULE_NOVELTY_V1_1', ?, ?)",
        (event_id, family_id, novelty_status, novelty_score, seen_at, seen_at),
    )


def main():
    with tempfile.TemporaryDirectory() as td:
        database = Database(Path(td) / "score.db")
        database.initialize()

        conn = database.connect()
        try:
            # 93 points: direct DART order + confirmed + money + NEW_EVENT.
            _insert_event(
                conn,
                event_id="S1",
                market_date="20260901",
                source_id="DART",
                source_grade="S",
                source_type="OFFICIAL",
                title="에이사 1조원 공급계약 체결",
                event_type="ORDER_CONTRACT",
                stage="CONFIRMED",
                novelty_status="NEW_EVENT",
                novelty_score=100,
                company="에이사",
                ticker="000001",
                numbers=("1조원",),
            )

            # 70 points: company-less but concrete official 25GW government policy.
            _insert_event(
                conn,
                event_id="S2",
                market_date="20260902",
                source_id="MOTIR",
                source_grade="S",
                source_type="GOV",
                title="2031년까지 해상풍력 25GW 보급 계획",
                event_type="GOV_POLICY",
                stage="PLANNED",
                novelty_status="NEW_EVENT",
                novelty_score=100,
                numbers=("25GW",),
            )

            # 61 points: named-company partnership announcement from a B-grade source.
            _insert_event(
                conn,
                event_id="S3",
                market_date="20260903",
                source_id="NEWS_B",
                source_grade="B",
                source_type="NEWS",
                title="씨사 전략적 협력 발표",
                event_type="PARTNERSHIP",
                stage="ANNOUNCED",
                novelty_status="NEW_EVENT",
                novelty_score=100,
                company="씨사",
                ticker="000003",
            )

            # 52 points: same low-impact setup but only a REHASH.
            _insert_event(
                conn,
                event_id="S4",
                market_date="20260904",
                source_id="NEWS_B",
                source_grade="B",
                source_type="NEWS",
                title="디사 전략적 협력 재조명",
                event_type="PARTNERSHIP",
                stage="ANNOUNCED",
                novelty_status="REHASH",
                novelty_score=15,
                company="디사",
                ticker="000004",
            )
            conn.commit()
        finally:
            conn.close()

        repository = MaterialScoreRepository(database)
        result = MaterialScorer(repository).run()
        assert result.processed == 4
        assert result.inserted == 4
        assert result.total_scores == 4
        assert result.strong == 1
        assert result.confirmed == 1
        assert result.watch == 1
        assert result.reject == 1

        conn = database.connect()
        try:
            rows = conn.execute(
                "SELECT event_id, material_score, material_status FROM material_scores ORDER BY event_id"
            ).fetchall()
        finally:
            conn.close()
        by_id = {row["event_id"]: row for row in rows}

        assert float(by_id["S1"]["material_score"]) == 93.0
        assert by_id["S1"]["material_status"] == "STRONG"
        assert float(by_id["S2"]["material_score"]) == 70.0
        assert by_id["S2"]["material_status"] == "CONFIRMED"
        assert float(by_id["S3"]["material_score"]) == 61.0
        assert by_id["S3"]["material_status"] == "WATCH"
        assert float(by_id["S4"]["material_score"]) == 52.0
        assert by_id["S4"]["material_status"] == "REJECT"

        repeat = MaterialScorer(repository).run()
        assert repeat.processed == 0
        assert repeat.total_scores == 4

        report = repository.export_report(Path(td) / "material_score_report.csv")
        assert report.exists()

    print("[OK] MaterialScorer V1 smoke test")
    print("     quantified DART order -> STRONG / 93")
    print("     concrete 25GW government policy -> CONFIRMED / 70")
    print("     lower-certainty partnership -> WATCH / 61")
    print("     rehash with weak impact -> REJECT / 52")
    print("     component sum -> 100 point scale")
    print("     incremental repeat -> processed=0")
    print("     material_score_report.csv -> OK")


if __name__ == "__main__":
    main()
