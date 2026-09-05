from __future__ import annotations

import csv
import json
from pathlib import Path

from ..novelty.family_builder import primary_company, primary_ticker
from ..novelty.models import EventView, NoveltyRecord
from .database import Database


class NoveltyRepository:
    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()

    @staticmethod
    def _eligible_sql(alias: str = "e", article_alias: str = "a") -> str:
        return f"({alias}.material_candidate = 1 OR COALESCE({article_alias}.article_class, '') = 'MARKET_REACTION')"

    def clear_all(self):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM event_novelty")
            conn.execute("DELETE FROM event_families")

    def prune_ineligible(self) -> int:
        with self.database.connect() as conn:
            before = int(conn.execute("SELECT COUNT(*) AS cnt FROM event_novelty").fetchone()["cnt"])
            conn.execute(
                "DELETE FROM event_novelty WHERE event_id NOT IN ("
                "SELECT e.event_id FROM material_events e "
                "LEFT JOIN articles a ON a.article_id = e.representative_article_id "
                f"WHERE {self._eligible_sql('e', 'a')}"
                ")"
            )
            after = int(conn.execute("SELECT COUNT(*) AS cnt FROM event_novelty").fetchone()["cnt"])
        return before - after

    def get_pending_events(self, *, analysis_version: str, limit: int | None = None):
        sql = (
            "SELECT e.*, a.source_grade, a.source_type, a.article_class "
            "FROM material_events e "
            "LEFT JOIN articles a ON a.article_id = e.representative_article_id "
            "LEFT JOIN event_novelty n ON n.event_id = e.event_id "
            f"WHERE {self._eligible_sql('e', 'a')} "
            "AND (n.event_id IS NULL OR n.analysis_version IS NULL OR n.analysis_version <> ? "
            "OR n.event_updated_at IS NULL OR n.event_updated_at <> e.updated_at) "
            "ORDER BY COALESCE(e.first_seen_at, e.created_at) ASC, e.event_id ASC"
        )
        params: list[object] = [analysis_version]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def get_prior_analyzed_events(
        self,
        current: EventView,
        *,
        start_market_date: str | None,
        limit: int = 500,
    ):
        sql = (
            "SELECT e.*, a.source_grade, a.source_type, a.article_class, n.family_id "
            "FROM event_novelty n "
            "JOIN material_events e ON e.event_id = n.event_id "
            "LEFT JOIN articles a ON a.article_id = e.representative_article_id "
            "WHERE n.event_id <> ? "
            f"AND {self._eligible_sql('e', 'a')} "
        )
        params: list[object] = [current.event_id]

        if current.market_date:
            if start_market_date:
                sql += "AND e.market_date >= ? "
                params.append(start_market_date)
            sql += (
                "AND (e.market_date < ? OR (e.market_date = ? AND "
                "COALESCE(e.first_seen_at, '') <= COALESCE(?, ''))) "
            )
            params.extend([current.market_date, current.market_date, current.first_seen_at or ""])
        elif current.first_seen_at:
            sql += "AND COALESCE(e.first_seen_at, '') <= ? "
            params.append(current.first_seen_at)

        sql += "ORDER BY COALESCE(e.first_seen_at, e.created_at) DESC, e.event_id DESC LIMIT ?"
        params.append(int(limit))
        with self.database.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def upsert_novelty(self, record: NoveltyRecord) -> tuple[str, str | None]:
        with self.database.connect() as conn:
            existing = conn.execute(
                "SELECT family_id FROM event_novelty WHERE event_id = ? LIMIT 1",
                (record.event_id,),
            ).fetchone()
            previous_family_id = existing["family_id"] if existing else None
            conn.execute(
                "INSERT INTO event_novelty("
                "event_id, family_id, parent_event_id, novelty_status, novelty_score, relation_score, "
                "days_since_parent, stage_changed, stage_progressed, number_changed, company_changed, "
                "polarity_changed, source_reliability_increased, confirmation_source_added, "
                "new_information_count, previous_stage, current_stage, previous_numbers_json, "
                "current_numbers_json, novelty_reason, analysis_version, event_updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "family_id=excluded.family_id, parent_event_id=excluded.parent_event_id, "
                "novelty_status=excluded.novelty_status, novelty_score=excluded.novelty_score, "
                "relation_score=excluded.relation_score, days_since_parent=excluded.days_since_parent, "
                "stage_changed=excluded.stage_changed, stage_progressed=excluded.stage_progressed, "
                "number_changed=excluded.number_changed, company_changed=excluded.company_changed, "
                "polarity_changed=excluded.polarity_changed, "
                "source_reliability_increased=excluded.source_reliability_increased, "
                "confirmation_source_added=excluded.confirmation_source_added, "
                "new_information_count=excluded.new_information_count, previous_stage=excluded.previous_stage, "
                "current_stage=excluded.current_stage, previous_numbers_json=excluded.previous_numbers_json, "
                "current_numbers_json=excluded.current_numbers_json, novelty_reason=excluded.novelty_reason, "
                "analysis_version=excluded.analysis_version, event_updated_at=excluded.event_updated_at, "
                "updated_at=CURRENT_TIMESTAMP",
                (
                    record.event_id,
                    record.family_id,
                    record.parent_event_id,
                    record.novelty_status,
                    float(record.novelty_score),
                    float(record.relation_score),
                    record.days_since_parent,
                    int(record.stage_changed),
                    int(record.stage_progressed),
                    int(record.number_changed),
                    int(record.company_changed),
                    int(record.polarity_changed),
                    int(record.source_reliability_increased),
                    int(record.confirmation_source_added),
                    int(record.new_information_count),
                    record.previous_stage,
                    record.current_stage,
                    json.dumps(record.previous_numbers, ensure_ascii=False),
                    json.dumps(record.current_numbers, ensure_ascii=False),
                    record.novelty_reason,
                    record.analysis_version,
                    record.event_updated_at,
                ),
            )
        return ("UPDATED" if existing else "INSERTED"), previous_family_id

    def refresh_family(self, family_id: str, *, analysis_version: str):
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT e.*, a.source_grade, a.source_type, a.article_class "
                "FROM event_novelty n "
                "JOIN material_events e ON e.event_id = n.event_id "
                "LEFT JOIN articles a ON a.article_id = e.representative_article_id "
                "WHERE n.family_id = ? "
                "ORDER BY COALESCE(e.first_seen_at, e.created_at) ASC, e.event_id ASC",
                (family_id,),
            ).fetchall()
        if not rows:
            with self.database.connect() as conn:
                conn.execute("DELETE FROM event_families WHERE family_id = ?", (family_id,))
            return

        first = EventView.from_row(rows[0])
        last = EventView.from_row(rows[-1])
        first_seen = min((row["first_seen_at"] for row in rows if row["first_seen_at"]), default=None)
        last_seen = max((row["last_seen_at"] for row in rows if row["last_seen_at"]), default=None)

        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO event_families("
                "family_id, root_event_id, latest_event_id, primary_company, primary_ticker, event_type, "
                "first_seen_at, last_seen_at, event_count, family_status, analysis_version"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?) "
                "ON CONFLICT(family_id) DO UPDATE SET "
                "root_event_id=excluded.root_event_id, latest_event_id=excluded.latest_event_id, "
                "primary_company=excluded.primary_company, primary_ticker=excluded.primary_ticker, "
                "event_type=excluded.event_type, first_seen_at=excluded.first_seen_at, "
                "last_seen_at=excluded.last_seen_at, event_count=excluded.event_count, "
                "family_status='ACTIVE', analysis_version=excluded.analysis_version, "
                "updated_at=CURRENT_TIMESTAMP",
                (
                    family_id,
                    first.event_id,
                    last.event_id,
                    primary_company(first),
                    primary_ticker(first),
                    first.event_type,
                    first_seen,
                    last_seen,
                    len(rows),
                    analysis_version,
                ),
            )

    def prune_empty_families(self):
        with self.database.connect() as conn:
            conn.execute(
                "DELETE FROM event_families WHERE family_id NOT IN "
                "(SELECT DISTINCT family_id FROM event_novelty)"
            )

    def novelty_count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS cnt FROM event_novelty").fetchone()["cnt"])

    def family_count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS cnt FROM event_families").fetchone()["cnt"])

    def status_counts(self) -> dict[str, int]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT novelty_status, COUNT(*) AS cnt FROM event_novelty GROUP BY novelty_status"
            ).fetchall()
        return {row["novelty_status"]: int(row["cnt"]) for row in rows}

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
                "SELECT n.*, e.market_date, e.event_type, e.event_stage, e.positive_negative, "
                "e.event_title, e.event_summary, e.companies_json, e.stock_codes_json, e.numbers_json, "
                "e.original_source_id, e.original_source_name, e.source_count, e.confirmation_count, "
                "e.first_seen_at, e.last_seen_at, f.root_event_id, f.event_count AS family_event_count "
                "FROM event_novelty n "
                "JOIN material_events e ON e.event_id = n.event_id "
                "LEFT JOIN event_families f ON f.family_id = n.family_id "
                "ORDER BY e.market_date DESC, n.novelty_score DESC, e.first_seen_at ASC"
            ).fetchall()

        fieldnames = [
            "event_id", "family_id", "parent_event_id", "root_event_id", "family_event_count",
            "market_date", "event_type", "event_stage", "positive_negative", "novelty_status",
            "novelty_score", "relation_score", "days_since_parent", "stage_changed",
            "stage_progressed", "number_changed", "company_changed", "polarity_changed",
            "source_reliability_increased", "confirmation_source_added", "new_information_count",
            "previous_stage", "current_stage", "previous_numbers", "current_numbers",
            "companies", "stock_codes", "numbers", "original_source_id", "original_source_name",
            "source_count", "confirmation_count", "event_title", "event_summary", "novelty_reason",
            "first_seen_at", "last_seen_at", "analysis_version",
        ]
        with output.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "event_id": row["event_id"],
                    "family_id": row["family_id"],
                    "parent_event_id": row["parent_event_id"],
                    "root_event_id": row["root_event_id"],
                    "family_event_count": row["family_event_count"],
                    "market_date": row["market_date"],
                    "event_type": row["event_type"],
                    "event_stage": row["event_stage"],
                    "positive_negative": row["positive_negative"],
                    "novelty_status": row["novelty_status"],
                    "novelty_score": row["novelty_score"],
                    "relation_score": row["relation_score"],
                    "days_since_parent": row["days_since_parent"],
                    "stage_changed": row["stage_changed"],
                    "stage_progressed": row["stage_progressed"],
                    "number_changed": row["number_changed"],
                    "company_changed": row["company_changed"],
                    "polarity_changed": row["polarity_changed"],
                    "source_reliability_increased": row["source_reliability_increased"],
                    "confirmation_source_added": row["confirmation_source_added"],
                    "new_information_count": row["new_information_count"],
                    "previous_stage": row["previous_stage"],
                    "current_stage": row["current_stage"],
                    "previous_numbers": self._json_pipe(row["previous_numbers_json"]),
                    "current_numbers": self._json_pipe(row["current_numbers_json"]),
                    "companies": self._json_pipe(row["companies_json"]),
                    "stock_codes": self._json_pipe(row["stock_codes_json"]),
                    "numbers": self._json_pipe(row["numbers_json"]),
                    "original_source_id": row["original_source_id"],
                    "original_source_name": row["original_source_name"],
                    "source_count": row["source_count"],
                    "confirmation_count": row["confirmation_count"],
                    "event_title": row["event_title"],
                    "event_summary": row["event_summary"],
                    "novelty_reason": row["novelty_reason"],
                    "first_seen_at": row["first_seen_at"],
                    "last_seen_at": row["last_seen_at"],
                    "analysis_version": row["analysis_version"],
                })
        return output
