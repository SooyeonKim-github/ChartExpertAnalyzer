from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from .storage import Database, TickerLinkRepository
from .ticker_linking import TickerLinker


def _write_csv(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_reference(root: Path):
    _write_csv(
        root / "ticker_master.csv",
        ["ticker", "name", "aliases", "market", "sector", "industry", "enabled"],
        [
            {"ticker": "005930", "name": "삼성전자", "aliases": "삼성전자㈜", "market": "KOSPI", "sector": "반도체", "industry": "반도체", "enabled": 1},
            {"ticker": "112610", "name": "씨에스윈드", "aliases": "", "market": "KOSPI", "sector": "풍력", "industry": "풍력", "enabled": 1},
            {"ticker": "100090", "name": "SK오션플랜트", "aliases": "", "market": "KOSPI", "sector": "풍력", "industry": "해상풍력", "enabled": 1},
            {"ticker": "999001", "name": "테스트장비", "aliases": "", "market": "KOSDAQ", "sector": "장비", "industry": "장비", "enabled": 1},
        ],
    )
    _write_csv(
        root / "event_theme_rules.csv",
        ["theme", "event_types", "keywords", "confidence", "enabled"],
        [
            {"theme": "해상풍력", "event_types": "GOV_POLICY", "keywords": "해상풍력|풍력발전", "confidence": 0.95, "enabled": 1},
            {"theme": "AI", "event_types": "AI|GOV_POLICY", "keywords": "인공지능|AI 산업", "confidence": 0.82, "enabled": 1},
        ],
    )
    _write_csv(
        root / "theme_ticker_map.csv",
        ["theme", "ticker", "name", "relation_type", "relation_weight", "confidence", "reason", "enabled"],
        [
            {"theme": "해상풍력", "ticker": "112610", "name": "씨에스윈드", "relation_type": "SECTOR", "relation_weight": 0.5, "confidence": 0.92, "reason": "wind tower", "enabled": 1},
            {"theme": "해상풍력", "ticker": "100090", "name": "SK오션플랜트", "relation_type": "SECTOR", "relation_weight": 0.5, "confidence": 0.88, "reason": "offshore structure", "enabled": 1},
            {"theme": "AI", "ticker": "005930", "name": "삼성전자", "relation_type": "THEME", "relation_weight": 0.35, "confidence": 0.75, "reason": "AI ecosystem", "enabled": 1},
        ],
    )
    _write_csv(
        root / "company_relationships.csv",
        ["subject_name", "subject_ticker", "related_ticker", "related_name", "relation_type", "relation_weight", "confidence", "evidence", "enabled"],
        [
            {"subject_name": "테스트고객", "subject_ticker": "999999", "related_ticker": "999001", "related_name": "테스트장비", "relation_type": "SUPPLIER", "relation_weight": 0.8, "confidence": 0.9, "evidence": "verified test supply relationship", "enabled": 1},
        ],
    )


def _insert(conn, event_id, title, event_type, score, status, *, company="", ticker="", summary="", polarity="POSITIVE"):
    seen = "2026-09-06T09:00:00+09:00"
    conn.execute(
        "INSERT INTO material_events("
        "event_id, cluster_id, representative_article_id, event_type, event_stage, event_title, event_summary, "
        "positive_negative, quantified, material_candidate, companies_json, stock_codes_json, numbers_json, "
        "original_source_id, original_source_name, article_count, source_count, confirmation_count, first_seen_at, "
        "last_seen_at, market_date, extraction_confidence, extraction_version, cluster_updated_at, updated_at"
        ") VALUES (?, ?, ?, ?, 'CONFIRMED', ?, ?, ?, 0, 1, ?, ?, '[]', 'TEST', 'TEST', 1, 1, 0, ?, ?, '20260906', 90, 'RULE_EVENT_V1_1', ?, ?)",
        (
            event_id, f"CL_{event_id}", f"A_{event_id}", event_type, title, summary or title, polarity,
            json.dumps([company] if company else [], ensure_ascii=False),
            json.dumps([ticker] if ticker else [], ensure_ascii=False),
            seen, seen, seen, seen,
        ),
    )
    conn.execute(
        "INSERT INTO material_scores("
        "event_id, material_score, material_status, direct_company_score, event_certainty_score, "
        "financial_impact_score, quantification_score, novelty_component_score, source_reliability_score, "
        "multi_source_score, scoring_reason, scoring_version, event_updated_at, novelty_updated_at, updated_at"
        ") VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 'test', 'RULE_MATERIAL_SCORE_V1_1', ?, ?, ?)",
        (event_id, score, status, seen, seen, seen),
    )


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ref = root / "reference"
        _write_reference(ref)
        database = Database(root / "ticker.db")
        database.initialize()

        conn = database.connect()
        try:
            _insert(conn, "E1", "삼성전자 직접 공시", "ORDER_CONTRACT", 90, "STRONG", company="삼성전자", ticker="005930")
            _insert(conn, "E2", "삼성전자 회사명만 확인", "ORDER_CONTRACT", 80, "CONFIRMED", company="삼성전자㈜")
            _insert(conn, "E3", "해상풍력 25GW 보급 계획", "GOV_POLICY", 70, "CONFIRMED")
            _insert(conn, "E4", "삼성전자 인공지능 투자", "AI", 82, "CONFIRMED", company="삼성전자")
            _insert(conn, "E5", "테스트고객 신규 장비 투자", "CAPEX", 88, "STRONG", company="테스트고객", ticker="999999")
            _insert(conn, "E6", "알수없는기업 신규사업", "PRODUCT", 60, "WATCH", company="알수없는기업")
            _insert(conn, "E7", "AI 산업 정책 참고자료", "GOV_POLICY", 50, "REJECT")
            conn.commit()
        finally:
            conn.close()

        repo = TickerLinkRepository(database)
        result = TickerLinker(repo, ref).run()
        assert result.processed == 7
        assert result.linked_events == 5
        assert result.unresolved_events == 2
        assert result.total_events == 7
        assert result.total_links == 7
        assert result.direct == 4
        assert result.supplier == 1
        assert result.sector == 2
        assert result.theme == 0

        conn = database.connect()
        try:
            rows = conn.execute(
                "SELECT event_id, ticker, relation_type, relation_weight, ticker_material_score "
                "FROM material_ticker_links ORDER BY event_id, ticker"
            ).fetchall()
        finally:
            conn.close()

        by_event = {}
        for row in rows:
            by_event.setdefault(row["event_id"], []).append(row)

        assert len(by_event["E1"]) == 1 and by_event["E1"][0]["relation_type"] == "DIRECT"
        assert by_event["E2"][0]["ticker"] == "005930" and by_event["E2"][0]["relation_type"] == "DIRECT"
        assert {row["ticker"] for row in by_event["E3"]} == {"112610", "100090"}
        assert all(row["relation_type"] == "SECTOR" for row in by_event["E3"])
        assert len(by_event["E4"]) == 1 and by_event["E4"][0]["relation_type"] == "DIRECT"
        assert {row["relation_type"] for row in by_event["E5"]} == {"DIRECT", "SUPPLIER"}
        assert float(next(row for row in by_event["E5"] if row["relation_type"] == "SUPPLIER")["ticker_material_score"]) == 70.4
        assert "E6" not in by_event
        assert "E7" not in by_event

        repeat = TickerLinker(repo, ref).run()
        assert repeat.processed == 0

        report = repo.export_report(root / "ticker_link_report.csv")
        unresolved = repo.export_unresolved(root / "ticker_link_unresolved.csv")
        assert report.exists() and unresolved.exists()

    print("[OK] TickerLinker V1 smoke test")
    print("     direct stock code -> DIRECT / 1.00")
    print("     exact company alias -> DIRECT")
    print("     company-less offshore wind policy -> SECTOR links")
    print("     direct company event -> no broad theme fan-out")
    print("     evidence-backed relationship -> SUPPLIER")
    print("     unknown company -> UNRESOLVED")
    print("     REJECT policy -> no theme expansion")
    print("     incremental repeat -> processed=0")
    print("     fuzzy company match / embeddings / LLM -> DISABLED")


if __name__ == "__main__":
    main()
