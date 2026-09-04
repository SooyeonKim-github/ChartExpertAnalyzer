from __future__ import annotations

import csv
import json
from pathlib import Path

from ..events.models import MaterialEvent
from .database import Database


class EventRepository:
    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()

    def clear_all(self):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM material_events")

    def prune_orphans(self) -> int:
        with self.database.connect() as conn:
            before = conn.execute("SELECT COUNT(*) AS cnt FROM material_events").fetchone()["cnt"]
            conn.execute(
                "DELETE FROM material_events WHERE cluster_id NOT IN "
                "(SELECT cluster_id FROM article_clusters WHERE cluster_status = 'ACTIVE')"
            )
            after = conn.execute("SELECT COUNT(*) AS cnt FROM material_events").fetchone()["cnt"]
        return int(before) - int(after)

    def get_pending_clusters(self, limit: int | None = None, extraction_version: str | None = None):
        sql = (
            "SELECT c.* FROM article_clusters c "
            "LEFT JOIN material_events e ON e.cluster_id = c.cluster_id "
            "WHERE c.cluster_status = 'ACTIVE' "
            "AND (e.event_id IS NULL OR e.cluster_updated_at IS NULL OR e.cluster_updated_at <> c.updated_at"
        )
        params: list[object] = []
        if extraction_version:
            sql += " OR e.extraction_version IS NULL OR e.extraction_version <> ?"
            params.append(extraction_version)
        sql += ") ORDER BY c.first_seen_at ASC, c.cluster_id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def get_cluster_members(self, cluster_id: str):
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT a.*, m.is_representative, m.match_score, m.match_method, m.match_reason "
                "FROM article_cluster_members m "
                "JOIN articles a ON a.article_id = m.article_id "
                "WHERE m.cluster_id = ? "
                "ORDER BY m.is_representative DESC, COALESCE(a.first_seen_at, a.collected_at) ASC",
                (cluster_id,),
            ).fetchall()

    def upsert_event(self, event: MaterialEvent) -> str:
        with self.database.connect() as conn:
            existed = conn.execute(
                "SELECT 1 FROM material_events WHERE event_id = ? LIMIT 1",
                (event.event_id,),
            ).fetchone() is not None
            conn.execute(
                "INSERT INTO material_events("
                "event_id, cluster_id, representative_article_id, event_type, event_stage, "
                "event_title, event_summary, positive_negative, quantified, material_candidate, "
                "material_candidate_reason, classification_source, companies_json, stock_codes_json, "
                "numbers_json, original_source_id, original_source_name, article_count, source_count, "
                "confirmation_count, first_seen_at, last_seen_at, market_date, extraction_confidence, "
                "extraction_version, cluster_updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "cluster_id=excluded.cluster_id, representative_article_id=excluded.representative_article_id, "
                "event_type=excluded.event_type, event_stage=excluded.event_stage, "
                "event_title=excluded.event_title, event_summary=excluded.event_summary, "
                "positive_negative=excluded.positive_negative, quantified=excluded.quantified, "
                "material_candidate=excluded.material_candidate, "
                "material_candidate_reason=excluded.material_candidate_reason, "
                "classification_source=excluded.classification_source, "
                "companies_json=excluded.companies_json, stock_codes_json=excluded.stock_codes_json, "
                "numbers_json=excluded.numbers_json, original_source_id=excluded.original_source_id, "
                "original_source_name=excluded.original_source_name, article_count=excluded.article_count, "
                "source_count=excluded.source_count, confirmation_count=excluded.confirmation_count, "
                "first_seen_at=excluded.first_seen_at, last_seen_at=excluded.last_seen_at, "
                "market_date=excluded.market_date, extraction_confidence=excluded.extraction_confidence, "
                "extraction_version=excluded.extraction_version, cluster_updated_at=excluded.cluster_updated_at, "
                "updated_at=CURRENT_TIMESTAMP",
                (
                    event.event_id, event.cluster_id, event.representative_article_id,
                    event.event_type, event.event_stage, event.event_title, event.event_summary,
                    event.positive_negative, int(event.quantified), int(event.material_candidate),
                    event.material_candidate_reason, event.classification_source,
                    json.dumps(event.companies, ensure_ascii=False),
                    json.dumps(event.stock_codes, ensure_ascii=False),
                    json.dumps(event.numbers, ensure_ascii=False),
                    event.original_source_id, event.original_source_name,
                    event.article_count, event.source_count, event.confirmation_count,
                    event.first_seen_at, event.last_seen_at, event.market_date,
                    event.extraction_confidence, event.extraction_version, event.cluster_updated_at,
                ),
            )
        return "UPDATED" if existed else "INSERTED"

    def event_count(self) -> int:
        with self.database.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM material_events").fetchone()
            return int(row["cnt"])

    def candidate_count(self) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM material_events WHERE material_candidate = 1"
            ).fetchone()
            return int(row["cnt"])

    @staticmethod
    def _json_pipe(value: str | None) -> str:
        if not value:
            return ""
        try:
            values = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return str(value)
        return "|".join(str(item) for item in values)

    def export_report(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM material_events "
                "ORDER BY material_candidate DESC, market_date DESC, extraction_confidence DESC, first_seen_at ASC"
            ).fetchall()

        fieldnames = [
            "event_id", "cluster_id", "market_date", "event_type", "event_stage",
            "positive_negative", "material_candidate", "material_candidate_reason",
            "classification_source", "event_title", "event_summary", "companies", "stock_codes",
            "numbers", "quantified", "original_source_id", "original_source_name",
            "article_count", "source_count", "confirmation_count", "first_seen_at", "last_seen_at",
            "extraction_confidence", "extraction_version", "representative_article_id",
        ]
        with output.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "event_id": row["event_id"],
                    "cluster_id": row["cluster_id"],
                    "market_date": row["market_date"],
                    "event_type": row["event_type"],
                    "event_stage": row["event_stage"],
                    "positive_negative": row["positive_negative"],
                    "material_candidate": row["material_candidate"],
                    "material_candidate_reason": row["material_candidate_reason"],
                    "classification_source": row["classification_source"],
                    "event_title": row["event_title"],
                    "event_summary": row["event_summary"],
                    "companies": self._json_pipe(row["companies_json"]),
                    "stock_codes": self._json_pipe(row["stock_codes_json"]),
                    "numbers": self._json_pipe(row["numbers_json"]),
                    "quantified": row["quantified"],
                    "original_source_id": row["original_source_id"],
                    "original_source_name": row["original_source_name"],
                    "article_count": row["article_count"],
                    "source_count": row["source_count"],
                    "confirmation_count": row["confirmation_count"],
                    "first_seen_at": row["first_seen_at"],
                    "last_seen_at": row["last_seen_at"],
                    "extraction_confidence": row["extraction_confidence"],
                    "extraction_version": row["extraction_version"],
                    "representative_article_id": row["representative_article_id"],
                })
        return output
