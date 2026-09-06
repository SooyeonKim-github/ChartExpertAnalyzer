from __future__ import annotations

import csv
import json
from pathlib import Path

from ..scoring.models import MaterialScoreRecord
from .database import Database


class MaterialScoreRepository:
    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()

    def clear_all(self):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM material_scores")

    def prune_ineligible(self) -> int:
        with self.database.connect() as conn:
            before = int(conn.execute("SELECT COUNT(*) AS cnt FROM material_scores").fetchone()["cnt"])
            conn.execute(
                "DELETE FROM material_scores WHERE event_id NOT IN ("
                "SELECT e.event_id FROM material_events e "
                "JOIN event_novelty n ON n.event_id = e.event_id "
                "WHERE e.material_candidate = 1 AND n.novelty_status <> 'MARKET_REACTION'"
                ")"
            )
            after = int(conn.execute("SELECT COUNT(*) AS cnt FROM material_scores").fetchone()["cnt"])
        return before - after

    def get_pending_events(self, *, scoring_version: str, limit: int | None = None):
        sql = (
            "SELECT e.*, a.source_grade, a.source_type, n.novelty_status, n.novelty_score, "
            "e.updated_at AS event_updated_at, n.updated_at AS novelty_updated_at "
            "FROM material_events e "
            "JOIN event_novelty n ON n.event_id = e.event_id "
            "LEFT JOIN articles a ON a.article_id = e.representative_article_id "
            "LEFT JOIN material_scores s ON s.event_id = e.event_id "
            "WHERE e.material_candidate = 1 AND n.novelty_status <> 'MARKET_REACTION' "
            "AND (s.event_id IS NULL OR s.scoring_version IS NULL OR s.scoring_version <> ? "
            "OR s.event_updated_at IS NULL OR s.event_updated_at <> e.updated_at "
            "OR s.novelty_updated_at IS NULL OR s.novelty_updated_at <> n.updated_at) "
            "ORDER BY COALESCE(e.first_seen_at, e.created_at) ASC, e.event_id ASC"
        )
        params: list[object] = [scoring_version]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def upsert_score(self, record: MaterialScoreRecord) -> str:
        with self.database.connect() as conn:
            existed = conn.execute(
                "SELECT 1 FROM material_scores WHERE event_id = ? LIMIT 1",
                (record.event_id,),
            ).fetchone() is not None
            conn.execute(
                "INSERT INTO material_scores("
                "event_id, material_score, material_status, direct_company_score, event_certainty_score, "
                "financial_impact_score, quantification_score, novelty_component_score, "
                "source_reliability_score, multi_source_score, scoring_reason, scoring_version, "
                "event_updated_at, novelty_updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "material_score=excluded.material_score, material_status=excluded.material_status, "
                "direct_company_score=excluded.direct_company_score, "
                "event_certainty_score=excluded.event_certainty_score, "
                "financial_impact_score=excluded.financial_impact_score, "
                "quantification_score=excluded.quantification_score, "
                "novelty_component_score=excluded.novelty_component_score, "
                "source_reliability_score=excluded.source_reliability_score, "
                "multi_source_score=excluded.multi_source_score, scoring_reason=excluded.scoring_reason, "
                "scoring_version=excluded.scoring_version, event_updated_at=excluded.event_updated_at, "
                "novelty_updated_at=excluded.novelty_updated_at, updated_at=CURRENT_TIMESTAMP",
                (
                    record.event_id,
                    float(record.material_score),
                    record.material_status,
                    float(record.direct_company_score),
                    float(record.event_certainty_score),
                    float(record.financial_impact_score),
                    float(record.quantification_score),
                    float(record.novelty_component_score),
                    float(record.source_reliability_score),
                    float(record.multi_source_score),
                    record.scoring_reason,
                    record.scoring_version,
                    record.event_updated_at,
                    record.novelty_updated_at,
                ),
            )
        return "UPDATED" if existed else "INSERTED"

    def score_count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS cnt FROM material_scores").fetchone()["cnt"])

    def status_counts(self) -> dict[str, int]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT material_status, COUNT(*) AS cnt FROM material_scores GROUP BY material_status"
            ).fetchall()
        return {row["material_status"]: int(row["cnt"]) for row in rows}

    @staticmethod
    def _json_pipe(value: str | None) -> str:
        if not value:
            return ""
        try:
            values = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return str(value)
        if not isinstance(values, list):
            return str(value)
        return "|".join(str(item) for item in values)

    def export_report(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT s.*, e.market_date, e.event_type, e.event_stage, e.positive_negative, "
                "e.event_title, e.event_summary, e.companies_json, e.stock_codes_json, e.numbers_json, "
                "e.original_source_id, e.original_source_name, e.source_count, e.confirmation_count, "
                "n.family_id, n.parent_event_id, n.novelty_status, n.novelty_score "
                "FROM material_scores s "
                "JOIN material_events e ON e.event_id = s.event_id "
                "JOIN event_novelty n ON n.event_id = s.event_id "
                "ORDER BY s.material_score DESC, e.market_date DESC, e.event_id ASC"
            ).fetchall()

        fieldnames = [
            "event_id", "family_id", "parent_event_id", "market_date", "material_status", "material_score",
            "event_type", "event_stage", "positive_negative", "novelty_status", "novelty_score",
            "direct_company_score", "event_certainty_score", "financial_impact_score",
            "quantification_score", "novelty_component_score", "source_reliability_score",
            "multi_source_score", "companies", "stock_codes", "numbers", "original_source_id",
            "original_source_name", "source_count", "confirmation_count", "event_title", "event_summary",
            "scoring_reason", "scoring_version",
        ]
        with output.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "event_id": row["event_id"],
                    "family_id": row["family_id"],
                    "parent_event_id": row["parent_event_id"],
                    "market_date": row["market_date"],
                    "material_status": row["material_status"],
                    "material_score": row["material_score"],
                    "event_type": row["event_type"],
                    "event_stage": row["event_stage"],
                    "positive_negative": row["positive_negative"],
                    "novelty_status": row["novelty_status"],
                    "novelty_score": row["novelty_score"],
                    "direct_company_score": row["direct_company_score"],
                    "event_certainty_score": row["event_certainty_score"],
                    "financial_impact_score": row["financial_impact_score"],
                    "quantification_score": row["quantification_score"],
                    "novelty_component_score": row["novelty_component_score"],
                    "source_reliability_score": row["source_reliability_score"],
                    "multi_source_score": row["multi_source_score"],
                    "companies": self._json_pipe(row["companies_json"]),
                    "stock_codes": self._json_pipe(row["stock_codes_json"]),
                    "numbers": self._json_pipe(row["numbers_json"]),
                    "original_source_id": row["original_source_id"],
                    "original_source_name": row["original_source_name"],
                    "source_count": row["source_count"],
                    "confirmation_count": row["confirmation_count"],
                    "event_title": row["event_title"],
                    "event_summary": row["event_summary"],
                    "scoring_reason": row["scoring_reason"],
                    "scoring_version": row["scoring_version"],
                })
        return output
