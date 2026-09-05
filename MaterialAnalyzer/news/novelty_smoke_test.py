from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .novelty import NoveltyAnalyzer
from .storage import Database, NoveltyRepository


def _insert_event(
    conn,
    *,
    event_id: str,
    market_date: str,
    source_id: str,
    source_grade: str,
    article_class: str,
    title: str,
    event_type: str,
    stage: str,
    company: str,
    ticker: str,
    numbers: tuple[str, ...] = (),
    polarity: str = "POSITIVE",
    material_candidate: bool = True,
):
    article_id = f"A_{event_id}"
    cluster_id = f"CL_{event_id}"
    seen_at = f"{market_date[:4]}-{market_date[4:6]}-{market_date[6:]}T09:00:00+09:00"

    conn.execute(
        "INSERT INTO articles("
        "article_id, source_id, endpoint_id, source_name, source_type, source_grade, title, url, "
        "collected_at, first_seen_at, last_seen_at, market_date, article_class"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            article_id,
            source_id,
            f"{source_id}_TEST",
            source_id,
            "NEWS" if source_id.startswith("NEWS") else "OFFICIAL",
            source_grade,
            title,
            f"https://example.com/{event_id}",
            seen_at,
            seen_at,
            seen_at,
            market_date,
            article_class,
        ),
    )
    conn.execute(
        "INSERT INTO material_events("
        "event_id, cluster_id, representative_article_id, event_type, event_stage, event_title, "
        "event_summary, positive_negative, quantified, material_candidate, material_candidate_reason, "
        "classification_source, companies_json, stock_codes_json, numbers_json, original_source_id, "
        "original_source_name, article_count, source_count, confirmation_count, first_seen_at, "
        "last_seen_at, market_date, extraction_confidence, extraction_version, cluster_updated_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TITLE', ?, ?, ?, ?, ?, 1, 1, 0, ?, ?, ?, 90, "
        "'RULE_EVENT_V1_1', ?, ?)",
        (
            event_id,
            cluster_id,
            article_id,
            event_type,
            stage,
            title,
            title,
            polarity,
            int(bool(numbers)),
            int(material_candidate),
            "MATERIAL_EVENT" if material_candidate else "MARKET_REACTION_ONLY",
            json.dumps([company] if company else [], ensure_ascii=False),
            json.dumps([ticker] if ticker else [], ensure_ascii=False),
            json.dumps(list(numbers), ensure_ascii=False),
            source_id,
            source_id,
            seen_at,
            seen_at,
            market_date,
            seen_at,
            seen_at,
        ),
    )


def main():
    with tempfile.TemporaryDirectory() as td:
        database = Database(Path(td) / "novelty.db")
        database.initialize()

        conn = database.connect()
        try:
            # One LNG contract family: NEW -> official CONFIRMATION -> REHASH -> amount FOLLOW_UP.
            _insert_event(
                conn,
                event_id="EV1",
                market_date="20260901",
                source_id="NEWS_A",
                source_grade="A",
                article_class="ORIGINAL_NEWS",
                title="에이사 LNG선 1조원 공급계약 체결",
                event_type="ORDER_CONTRACT",
                stage="CONFIRMED",
                company="에이사",
                ticker="000001",
                numbers=("1조원",),
            )
            _insert_event(
                conn,
                event_id="EV2",
                market_date="20260902",
                source_id="DART",
                source_grade="S",
                article_class="DISCLOSURE",
                title="에이사 LNG선 1조원 공급계약 체결",
                event_type="ORDER_CONTRACT",
                stage="CONFIRMED",
                company="에이사",
                ticker="000001",
                numbers=("1조원",),
            )
            _insert_event(
                conn,
                event_id="EV3",
                market_date="20260903",
                source_id="NEWS_A",
                source_grade="A",
                article_class="ORIGINAL_NEWS",
                title="에이사 LNG선 1조원 공급계약 체결",
                event_type="ORDER_CONTRACT",
                stage="CONFIRMED",
                company="에이사",
                ticker="000001",
                numbers=("1조원",),
            )
            _insert_event(
                conn,
                event_id="EV4",
                market_date="20260904",
                source_id="NEWS_A",
                source_grade="A",
                article_class="ORIGINAL_NEWS",
                title="에이사 LNG선 1.5조원 공급계약 체결",
                event_type="ORDER_CONTRACT",
                stage="CONFIRMED",
                company="에이사",
                ticker="000001",
                numbers=("1.5조원",),
            )

            # Same-looking event at another company must remain NEW.
            _insert_event(
                conn,
                event_id="EV5",
                market_date="20260904",
                source_id="NEWS_A",
                source_grade="A",
                article_class="ORIGINAL_NEWS",
                title="비사 LNG선 1조원 공급계약 체결",
                event_type="ORDER_CONTRACT",
                stage="CONFIRMED",
                company="비사",
                ticker="000002",
                numbers=("1조원",),
            )

            # Stage progression is a FOLLOW_UP.
            _insert_event(
                conn,
                event_id="EV6",
                market_date="20260905",
                source_id="NEWS_A",
                source_grade="A",
                article_class="ORIGINAL_NEWS",
                title="에이사 신규 공장 5000억원 설비투자 계획",
                event_type="CAPEX",
                stage="PLANNED",
                company="에이사",
                ticker="000001",
                numbers=("5000억원",),
            )
            _insert_event(
                conn,
                event_id="EV7",
                market_date="20260906",
                source_id="DART",
                source_grade="S",
                article_class="DISCLOSURE",
                title="에이사 신규 공장 5000억원 설비투자 확정",
                event_type="CAPEX",
                stage="CONFIRMED",
                company="에이사",
                ticker="000001",
                numbers=("5000억원",),
            )

            # A reaction is tracked but is not a new catalyst.
            _insert_event(
                conn,
                event_id="EV8",
                market_date="20260907",
                source_id="NEWS_A",
                source_grade="A",
                article_class="MARKET_REACTION",
                title="에이사 LNG선 수주 소식에 주가 급등",
                event_type="ORDER_CONTRACT",
                stage="ANNOUNCED",
                company="에이사",
                ticker="000001",
                material_candidate=False,
            )

            # Same company + same event type, but a different contract anchor must stay NEW.
            _insert_event(
                conn,
                event_id="EV9",
                market_date="20260908",
                source_id="NEWS_A",
                source_grade="A",
                article_class="ORIGINAL_NEWS",
                title="에이사 반도체 장비 공급계약 체결",
                event_type="ORDER_CONTRACT",
                stage="CONFIRMED",
                company="에이사",
                ticker="000001",
            )
            conn.commit()
        finally:
            conn.close()

        repository = NoveltyRepository(database)
        result = NoveltyAnalyzer(repository).run()

        assert result.processed == 9
        assert result.total_novelty == 9
        assert result.new_event == 4
        assert result.confirmation == 1
        assert result.rehash == 1
        assert result.follow_up == 2
        assert result.market_reaction == 1
        assert result.total_families == 4

        conn = database.connect()
        try:
            rows = conn.execute(
                "SELECT event_id, family_id, parent_event_id, novelty_status, number_changed, "
                "stage_progressed FROM event_novelty ORDER BY event_id"
            ).fetchall()
        finally:
            conn.close()
        by_id = {row["event_id"]: row for row in rows}

        assert by_id["EV1"]["novelty_status"] == "NEW_EVENT"
        assert by_id["EV2"]["novelty_status"] == "CONFIRMATION"
        assert by_id["EV3"]["novelty_status"] == "REHASH"
        assert by_id["EV4"]["novelty_status"] == "FOLLOW_UP"
        assert int(by_id["EV4"]["number_changed"]) == 1
        assert by_id["EV5"]["novelty_status"] == "NEW_EVENT"
        assert by_id["EV7"]["novelty_status"] == "FOLLOW_UP"
        assert int(by_id["EV7"]["stage_progressed"]) == 1
        assert by_id["EV8"]["novelty_status"] == "MARKET_REACTION"
        assert by_id["EV9"]["novelty_status"] == "NEW_EVENT"

        assert by_id["EV1"]["family_id"] == by_id["EV2"]["family_id"]
        assert by_id["EV1"]["family_id"] == by_id["EV4"]["family_id"]
        assert by_id["EV1"]["family_id"] != by_id["EV9"]["family_id"]

        repeat = NoveltyAnalyzer(repository).run()
        assert repeat.processed == 0
        assert repeat.total_novelty == 9

        report = repository.export_report(Path(td) / "novelty_report.csv")
        assert report.exists()

    print("[OK] NoveltyAnalyzer V1 smoke test")
    print("     first material -> NEW_EVENT")
    print("     same event upgraded to DART -> CONFIRMATION")
    print("     same content without delta -> REHASH")
    print("     meaningful amount change -> FOLLOW_UP")
    print("     stage progression -> FOLLOW_UP")
    print("     market reaction -> MARKET_REACTION")
    print("     different company -> separate NEW_EVENT")
    print("     same company, different contract anchor -> separate NEW_EVENT")
    print("     incremental repeat -> processed=0")
    print("     novelty_report.csv -> OK")
    print("     embeddings / semantic similarity -> DISABLED")


if __name__ == "__main__":
    main()
