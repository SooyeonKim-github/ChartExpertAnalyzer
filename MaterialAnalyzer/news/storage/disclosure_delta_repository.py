from __future__ import annotations

import csv
import json
from pathlib import Path

from ..disclosure_delta.models import DisclosureDeltaInput, DisclosureDeltaRecord
from .database import Database


DISCLOSURE_DELTA_SCHEMA = """
CREATE TABLE IF NOT EXISTS disclosure_deltas (
    event_id TEXT PRIMARY KEY,
    parent_event_id TEXT,
    is_revision INTEGER NOT NULL DEFAULT 0,
    parent_match_method TEXT,
    parent_match_confidence REAL NOT NULL DEFAULT 0,
    delta_type TEXT NOT NULL,
    delta_direction TEXT NOT NULL DEFAULT 'NONE',
    previous_numbers_json TEXT,
    current_numbers_json TEXT,
    numeric_kind TEXT,
    previous_numeric_value REAL,
    current_numeric_value REAL,
    numeric_change REAL,
    numeric_change_pct REAL,
    effective_sentiment TEXT NOT NULL DEFAULT 'NEUTRAL',
    score_adjustment REAL NOT NULL DEFAULT 0,
    delta_reason TEXT,
    analysis_version TEXT NOT NULL,
    event_updated_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_disclosure_deltas_parent ON disclosure_deltas(parent_event_id);
CREATE INDEX IF NOT EXISTS idx_disclosure_deltas_type ON disclosure_deltas(delta_type);
CREATE INDEX IF NOT EXISTS idx_disclosure_deltas_revision ON disclosure_deltas(is_revision);
"""


class DisclosureDeltaRepository:
    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()
        with self.database.connect() as conn:
            conn.executescript(DISCLOSURE_DELTA_SCHEMA)

    def clear_all(self):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM disclosure_deltas")

    def prune_orphans(self):
        with self.database.connect() as conn:
            conn.execute(
                "DELETE FROM disclosure_deltas WHERE event_id NOT IN (SELECT event_id FROM material_events)"
            )

    def get_pending_events(self, *, analysis_version: str, limit: int | None = None):
        sql = (
            "SELECT e.* FROM material_events e "
            "LEFT JOIN disclosure_deltas d ON d.event_id = e.event_id "
            "LEFT JOIN articles a ON a.article_id = e.representative_article_id "
            "WHERE (e.original_source_id IN ('DART','KIND') OR COALESCE(a.article_class,'') = 'DISCLOSURE') "
            "AND (d.event_id IS NULL OR d.analysis_version <> ? "
            "OR COALESCE(d.event_updated_at,'') <> COALESCE(e.updated_at,'')) "
            "ORDER BY COALESCE(e.first_seen_at,e.created_at) ASC,e.event_id ASC"
        )
        params: list[object] = [analysis_version]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def find_exact_canonical_parent(self, event: DisclosureDeltaInput):
        if not event.canonical_event_key:
            return None
        sql = (
            "SELECT * FROM material_events WHERE event_id <> ? AND canonical_event_key = ? "
            "AND COALESCE(first_seen_at,created_at) <= COALESCE(?,COALESCE(first_seen_at,created_at)) "
            "ORDER BY COALESCE(first_seen_at,created_at) DESC,event_id DESC LIMIT 2"
        )
        with self.database.connect() as conn:
            rows = conn.execute(
                sql,
                (event.event_id, event.canonical_event_key, event.first_seen_at),
            ).fetchall()
        return rows[0] if len(rows) == 1 else None

    def find_revision_candidates(self, event: DisclosureDeltaInput, *, limit: int = 50):
        companies_json = json.dumps(event.companies, ensure_ascii=False)
        stock_codes_json = json.dumps(event.stock_codes, ensure_ascii=False)
        sql = (
            "SELECT * FROM material_events WHERE event_id <> ? AND event_type = ? "
            "AND original_source_id IN ('DART','KIND') "
            "AND COALESCE(first_seen_at,created_at) <= COALESCE(?,COALESCE(first_seen_at,created_at)) "
            "AND ((? <> '[]' AND stock_codes_json = ?) OR (? <> '[]' AND companies_json = ?)) "
            "ORDER BY COALESCE(first_seen_at,created_at) DESC,event_id DESC LIMIT ?"
        )
        with self.database.connect() as conn:
            return conn.execute(
                sql,
                (
                    event.event_id,
                    event.event_type,
                    event.first_seen_at,
                    stock_codes_json,
                    stock_codes_json,
                    companies_json,
                    companies_json,
                    int(limit),
                ),
            ).fetchall()

    def upsert(self, record: DisclosureDeltaRecord) -> str:
        with self.database.connect() as conn:
            existed = conn.execute(
                "SELECT 1 FROM disclosure_deltas WHERE event_id=? LIMIT 1",
                (record.event_id,),
            ).fetchone() is not None
            conn.execute(
                "INSERT INTO disclosure_deltas("
                "event_id,parent_event_id,is_revision,parent_match_method,parent_match_confidence,"
                "delta_type,delta_direction,previous_numbers_json,current_numbers_json,numeric_kind,"
                "previous_numeric_value,current_numeric_value,numeric_change,numeric_change_pct,"
                "effective_sentiment,score_adjustment,delta_reason,analysis_version,event_updated_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "parent_event_id=excluded.parent_event_id,is_revision=excluded.is_revision,"
                "parent_match_method=excluded.parent_match_method,parent_match_confidence=excluded.parent_match_confidence,"
                "delta_type=excluded.delta_type,delta_direction=excluded.delta_direction,"
                "previous_numbers_json=excluded.previous_numbers_json,current_numbers_json=excluded.current_numbers_json,"
                "numeric_kind=excluded.numeric_kind,previous_numeric_value=excluded.previous_numeric_value,"
                "current_numeric_value=excluded.current_numeric_value,numeric_change=excluded.numeric_change,"
                "numeric_change_pct=excluded.numeric_change_pct,effective_sentiment=excluded.effective_sentiment,"
                "score_adjustment=excluded.score_adjustment,delta_reason=excluded.delta_reason,"
                "analysis_version=excluded.analysis_version,event_updated_at=excluded.event_updated_at,"
                "updated_at=CURRENT_TIMESTAMP",
                (
                    record.event_id,
                    record.parent_event_id,
                    int(record.is_revision),
                    record.parent_match_method,
                    record.parent_match_confidence,
                    record.delta_type,
                    record.delta_direction,
                    json.dumps(record.previous_numbers, ensure_ascii=False),
                    json.dumps(record.current_numbers, ensure_ascii=False),
                    record.numeric_kind,
                    record.previous_numeric_value,
                    record.current_numeric_value,
                    record.numeric_change,
                    record.numeric_change_pct,
                    record.effective_sentiment,
                    record.score_adjustment,
                    record.delta_reason,
                    record.analysis_version,
                    record.event_updated_at,
                ),
            )
        return "UPDATED" if existed else "INSERTED"

    def count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS cnt FROM disclosure_deltas").fetchone()["cnt"])

    def delta_type_counts(self) -> dict[str, int]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT delta_type,COUNT(*) AS cnt FROM disclosure_deltas GROUP BY delta_type"
            ).fetchall()
        return {row["delta_type"]: int(row["cnt"]) for row in rows}

    @staticmethod
    def _json_pipe(value: str | None) -> str:
        if not value:
            return ""
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return str(value)
        return "|".join(str(x) for x in parsed) if isinstance(parsed, list) else str(value)

    def export_report(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT d.*,e.market_date,e.canonical_event_key,e.document_signature,e.event_type,e.event_title,"
                "e.positive_negative,e.companies_json,e.stock_codes_json "
                "FROM disclosure_deltas d JOIN material_events e ON e.event_id=d.event_id "
                "ORDER BY e.market_date DESC,d.is_revision DESC,e.event_id ASC"
            ).fetchall()
        fields = [
            "event_id","parent_event_id","market_date","canonical_event_key","document_signature","event_type",
            "is_revision","parent_match_method","parent_match_confidence","delta_type","delta_direction",
            "original_sentiment","effective_sentiment","score_adjustment","numeric_kind","previous_numeric_value",
            "current_numeric_value","numeric_change","numeric_change_pct","previous_numbers","current_numbers",
            "companies","stock_codes","event_title","delta_reason","analysis_version",
        ]
        with output.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "event_id": row["event_id"],
                    "parent_event_id": row["parent_event_id"],
                    "market_date": row["market_date"],
                    "canonical_event_key": row["canonical_event_key"],
                    "document_signature": row["document_signature"],
                    "event_type": row["event_type"],
                    "is_revision": row["is_revision"],
                    "parent_match_method": row["parent_match_method"],
                    "parent_match_confidence": row["parent_match_confidence"],
                    "delta_type": row["delta_type"],
                    "delta_direction": row["delta_direction"],
                    "original_sentiment": row["positive_negative"],
                    "effective_sentiment": row["effective_sentiment"],
                    "score_adjustment": row["score_adjustment"],
                    "numeric_kind": row["numeric_kind"],
                    "previous_numeric_value": row["previous_numeric_value"],
                    "current_numeric_value": row["current_numeric_value"],
                    "numeric_change": row["numeric_change"],
                    "numeric_change_pct": row["numeric_change_pct"],
                    "previous_numbers": self._json_pipe(row["previous_numbers_json"]),
                    "current_numbers": self._json_pipe(row["current_numbers_json"]),
                    "companies": self._json_pipe(row["companies_json"]),
                    "stock_codes": self._json_pipe(row["stock_codes_json"]),
                    "event_title": row["event_title"],
                    "delta_reason": row["delta_reason"],
                    "analysis_version": row["analysis_version"],
                })
        return output
