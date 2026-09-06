from __future__ import annotations

import csv
import json
from pathlib import Path

from ..ticker_linking.models import LinkInput, TickerLinkRecord
from .database import Database


TICKER_LINK_SCHEMA = """
CREATE TABLE IF NOT EXISTS material_ticker_links (
    event_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    relation_weight REAL NOT NULL,
    mapping_relevance REAL NOT NULL DEFAULT 1,
    link_confidence REAL NOT NULL,
    theme TEXT,
    theme_materiality_score REAL NOT NULL DEFAULT 0,
    link_reason TEXT,
    evidence TEXT,
    material_score REAL NOT NULL,
    material_status TEXT NOT NULL,
    ticker_material_score REAL NOT NULL,
    positive_negative TEXT NOT NULL,
    link_version TEXT NOT NULL,
    reference_signature TEXT,
    event_updated_at TEXT,
    score_updated_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(event_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_material_ticker_links_ticker ON material_ticker_links(ticker);
CREATE INDEX IF NOT EXISTS idx_material_ticker_links_relation ON material_ticker_links(relation_type);
CREATE INDEX IF NOT EXISTS idx_material_ticker_links_score ON material_ticker_links(ticker_material_score DESC);

CREATE TABLE IF NOT EXISTS ticker_link_states (
    event_id TEXT PRIMARY KEY,
    link_version TEXT NOT NULL,
    reference_signature TEXT,
    event_updated_at TEXT,
    score_updated_at TEXT,
    linked_count INTEGER NOT NULL DEFAULT 0,
    unresolved_reason TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

LINK_MIGRATIONS = {
    "mapping_relevance": "REAL NOT NULL DEFAULT 1",
    "theme_materiality_score": "REAL NOT NULL DEFAULT 0",
    "reference_signature": "TEXT",
}
STATE_MIGRATIONS = {"reference_signature": "TEXT"}


class TickerLinkRepository:
    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()
        conn = self.database.connect()
        try:
            conn.executescript(TICKER_LINK_SCHEMA)
            self._migrate(conn)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _migrate(conn):
        link_cols = {row[1] for row in conn.execute("PRAGMA table_info(material_ticker_links)")}
        for column, definition in LINK_MIGRATIONS.items():
            if column not in link_cols:
                conn.execute(f"ALTER TABLE material_ticker_links ADD COLUMN {column} {definition}")
        state_cols = {row[1] for row in conn.execute("PRAGMA table_info(ticker_link_states)")}
        for column, definition in STATE_MIGRATIONS.items():
            if column not in state_cols:
                conn.execute(f"ALTER TABLE ticker_link_states ADD COLUMN {column} {definition}")

    @staticmethod
    def _json_list(value) -> list[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        return [str(item) for item in parsed if str(item)] if isinstance(parsed, list) else []

    def clear_all(self):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM material_ticker_links")
            conn.execute("DELETE FROM ticker_link_states")

    def prune_orphans(self):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM material_ticker_links WHERE event_id NOT IN (SELECT event_id FROM material_scores)")
            conn.execute("DELETE FROM ticker_link_states WHERE event_id NOT IN (SELECT event_id FROM material_scores)")

    def get_pending_events(self, *, link_version: str, reference_signature: str, limit: int | None = None):
        sql = (
            "SELECT e.*, e.updated_at AS event_updated_at, s.material_score, s.material_status, "
            "s.updated_at AS score_updated_at, n.novelty_status, a.source_grade, a.source_type "
            "FROM material_scores s "
            "JOIN material_events e ON e.event_id = s.event_id "
            "LEFT JOIN event_novelty n ON n.event_id = e.event_id "
            "LEFT JOIN articles a ON a.article_id = e.representative_article_id "
            "LEFT JOIN ticker_link_states t ON t.event_id = e.event_id "
            "WHERE t.event_id IS NULL OR t.link_version <> ? "
            "OR COALESCE(t.reference_signature, '') <> ? "
            "OR COALESCE(t.event_updated_at, '') <> COALESCE(e.updated_at, '') "
            "OR COALESCE(t.score_updated_at, '') <> COALESCE(s.updated_at, '') "
            "ORDER BY e.market_date ASC, COALESCE(e.first_seen_at, e.created_at) ASC, e.event_id ASC"
        )
        params: list[object] = [link_version, reference_signature]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def get_direct_identity_pairs(self):
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT companies_json, stock_codes_json FROM material_events WHERE material_candidate = 1"
            ).fetchall()
        pairs, seen = [], set()
        for row in rows:
            companies = self._json_list(row["companies_json"])
            tickers = self._json_list(row["stock_codes_json"])
            if len(companies) == 1 and len(tickers) == 1:
                pair = (tickers[0].zfill(6), companies[0])
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)
        return pairs

    def replace_event_links(self, event: LinkInput, links: list[TickerLinkRecord], link_version: str,
                            reference_signature: str, unresolved_reason: str = ""):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM material_ticker_links WHERE event_id = ?", (event.event_id,))
            for row in links:
                conn.execute(
                    "INSERT INTO material_ticker_links("
                    "event_id,ticker,name,relation_type,relation_weight,mapping_relevance,link_confidence,theme,"
                    "theme_materiality_score,link_reason,evidence,material_score,material_status,ticker_material_score,"
                    "positive_negative,link_version,reference_signature,event_updated_at,score_updated_at"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row.event_id, row.ticker, row.name, row.relation_type, row.relation_weight,
                        row.mapping_relevance, row.link_confidence, row.theme, row.theme_materiality_score,
                        row.link_reason, row.evidence, row.material_score, row.material_status,
                        row.ticker_material_score, row.positive_negative, row.link_version,
                        row.reference_signature, row.event_updated_at, row.score_updated_at,
                    ),
                )
            conn.execute(
                "INSERT INTO ticker_link_states(event_id,link_version,reference_signature,event_updated_at,score_updated_at,linked_count,unresolved_reason) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET "
                "link_version=excluded.link_version,reference_signature=excluded.reference_signature,"
                "event_updated_at=excluded.event_updated_at,score_updated_at=excluded.score_updated_at,"
                "linked_count=excluded.linked_count,unresolved_reason=excluded.unresolved_reason,updated_at=CURRENT_TIMESTAMP",
                (event.event_id, link_version, reference_signature, event.event_updated_at,
                 event.score_updated_at, len(links), unresolved_reason),
            )

    def link_count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS cnt FROM material_ticker_links").fetchone()["cnt"])

    def state_count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS cnt FROM ticker_link_states").fetchone()["cnt"])

    def relation_counts(self) -> dict[str, int]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT relation_type, COUNT(*) AS cnt FROM material_ticker_links GROUP BY relation_type").fetchall()
        return {row["relation_type"]: int(row["cnt"]) for row in rows}

    def export_report(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT l.*, e.market_date,e.event_type,e.event_stage,e.event_title,e.event_summary,"
                "e.companies_json,e.stock_codes_json,n.novelty_status FROM material_ticker_links l "
                "JOIN material_events e ON e.event_id=l.event_id "
                "LEFT JOIN event_novelty n ON n.event_id=l.event_id "
                "ORDER BY e.market_date DESC,l.ticker_material_score DESC,l.link_confidence DESC"
            ).fetchall()
        fields = [
            "event_id","market_date","ticker","name","relation_type","relation_weight","mapping_relevance",
            "link_confidence","theme","theme_materiality_score","material_score","material_status",
            "ticker_material_score","positive_negative","novelty_status","event_type","event_stage","companies",
            "direct_stock_codes","event_title","event_summary","link_reason","evidence","link_version","reference_signature",
        ]
        with output.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "event_id":row["event_id"], "market_date":row["market_date"], "ticker":row["ticker"],
                    "name":row["name"], "relation_type":row["relation_type"], "relation_weight":row["relation_weight"],
                    "mapping_relevance":row["mapping_relevance"], "link_confidence":row["link_confidence"],
                    "theme":row["theme"], "theme_materiality_score":row["theme_materiality_score"],
                    "material_score":row["material_score"], "material_status":row["material_status"],
                    "ticker_material_score":row["ticker_material_score"], "positive_negative":row["positive_negative"],
                    "novelty_status":row["novelty_status"], "event_type":row["event_type"], "event_stage":row["event_stage"],
                    "companies":"|".join(self._json_list(row["companies_json"])),
                    "direct_stock_codes":"|".join(self._json_list(row["stock_codes_json"])),
                    "event_title":row["event_title"], "event_summary":row["event_summary"],
                    "link_reason":row["link_reason"], "evidence":row["evidence"],
                    "link_version":row["link_version"], "reference_signature":row["reference_signature"],
                })
        return output

    def export_unresolved(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT t.event_id,e.market_date,e.event_type,e.event_title,e.companies_json,"
                "s.material_score,s.material_status,t.unresolved_reason FROM ticker_link_states t "
                "JOIN material_events e ON e.event_id=t.event_id JOIN material_scores s ON s.event_id=t.event_id "
                "WHERE t.linked_count=0 ORDER BY s.material_score DESC,e.market_date DESC"
            ).fetchall()
        fields = ["event_id","market_date","event_type","material_score","material_status","companies","event_title","unresolved_reason"]
        with output.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "event_id":row["event_id"], "market_date":row["market_date"], "event_type":row["event_type"],
                    "material_score":row["material_score"], "material_status":row["material_status"],
                    "companies":"|".join(self._json_list(row["companies_json"])), "event_title":row["event_title"],
                    "unresolved_reason":row["unresolved_reason"],
                })
        return output
