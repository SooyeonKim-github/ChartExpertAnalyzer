from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    external_id TEXT,
    source_name TEXT,
    source_type TEXT,
    source_grade TEXT,
    title TEXT NOT NULL,
    body TEXT,
    summary TEXT,
    url TEXT NOT NULL,
    canonical_url TEXT,
    author TEXT,
    published_at TEXT,
    updated_at TEXT,
    collected_at TEXT NOT NULL,
    published_at_precision TEXT DEFAULT 'UNKNOWN',
    first_seen_at TEXT,
    last_seen_at TEXT,
    published_date TEXT,
    market_date TEXT,
    category TEXT,
    language TEXT DEFAULT 'ko',
    article_class TEXT,
    collector_type TEXT,
    content_mode TEXT,
    url_hash TEXT,
    title_hash TEXT,
    content_hash TEXT,
    duplicate_of TEXT,
    body_length INTEGER DEFAULT 0,
    has_full_body INTEGER DEFAULT 0,
    fetch_status TEXT,
    http_status INTEGER,
    parse_status TEXT,
    error_code TEXT,
    material_candidate INTEGER DEFAULT 0,
    analysis_status TEXT DEFAULT 'PENDING',
    processed_at TEXT,
    source_metadata_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_db_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_article_id ON articles(article_id);
CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles(url_hash);
CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id, endpoint_id);

CREATE TABLE IF NOT EXISTS source_states (
    source_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    health_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_started_at TEXT,
    last_success_at TEXT,
    last_failure_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_discovered_count INTEGER NOT NULL DEFAULT 0,
    last_fetched_count INTEGER NOT NULL DEFAULT 0,
    last_inserted_count INTEGER NOT NULL DEFAULT 0,
    last_updated_count INTEGER NOT NULL DEFAULT 0,
    last_duplicated_count INTEGER NOT NULL DEFAULT 0,
    last_skipped_count INTEGER NOT NULL DEFAULT 0,
    last_failed_count INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT,
    last_error_message TEXT,
    checkpoint_value TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source_id, endpoint_id)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    health_status TEXT,
    discovered INTEGER NOT NULL DEFAULT 0,
    fetched INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    duplicated INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    checkpoint_value TEXT,
    error_code TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_collection_runs_source_time
ON collection_runs(source_id, endpoint_id, started_at DESC);
"""


MIGRATION_COLUMNS = {
    "external_id": "TEXT",
    "published_at_precision": "TEXT DEFAULT 'UNKNOWN'",
    "first_seen_at": "TEXT",
    "last_seen_at": "TEXT",
}


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate_columns(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_first_seen_at ON articles(first_seen_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_market_date ON articles(market_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_external_id ON articles(source_id, external_id)")

    @staticmethod
    def _migrate_columns(conn: sqlite3.Connection):
        existing = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
        for column, definition in MIGRATION_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE articles ADD COLUMN {column} {definition}")

        # Existing V1.x rows already use SOURCE_externalId-style article ids for most
        # adapters. Backfill an incremental key where possible; URL hash remains the
        # fallback for rows whose article_id contains an internally generated hash.
        conn.execute(
            "UPDATE articles SET external_id = CASE "
            "WHEN external_id IS NOT NULL AND external_id <> '' THEN external_id "
            "WHEN article_id LIKE source_id || '_%' THEN substr(article_id, length(source_id) + 2) "
            "ELSE external_id END"
        )
        conn.execute(
            "UPDATE articles SET first_seen_at = COALESCE(first_seen_at, collected_at), "
            "last_seen_at = COALESCE(last_seen_at, collected_at)"
        )
