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

CREATE TABLE IF NOT EXISTS article_clusters (
    cluster_id TEXT PRIMARY KEY,
    representative_article_id TEXT NOT NULL,
    cluster_title TEXT NOT NULL,
    event_key TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    market_date TEXT,
    article_count INTEGER NOT NULL DEFAULT 0,
    source_count INTEGER NOT NULL DEFAULT 0,
    confirmation_count INTEGER NOT NULL DEFAULT 0,
    cluster_confidence REAL,
    cluster_status TEXT NOT NULL DEFAULT 'ACTIVE',
    clustering_version TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_article_clusters_market_date
ON article_clusters(market_date);
CREATE INDEX IF NOT EXISTS idx_article_clusters_event_key
ON article_clusters(event_key);

CREATE TABLE IF NOT EXISTS article_cluster_members (
    cluster_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    match_score REAL NOT NULL DEFAULT 0,
    match_method TEXT NOT NULL,
    match_reason TEXT,
    is_representative INTEGER NOT NULL DEFAULT 0,
    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(cluster_id, article_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cluster_members_article
ON article_cluster_members(article_id);
CREATE INDEX IF NOT EXISTS idx_cluster_members_cluster
ON article_cluster_members(cluster_id);

CREATE TABLE IF NOT EXISTS material_events (
    event_id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL UNIQUE,
    representative_article_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_stage TEXT NOT NULL,
    event_title TEXT NOT NULL,
    event_summary TEXT,
    positive_negative TEXT NOT NULL DEFAULT 'NEUTRAL',
    quantified INTEGER NOT NULL DEFAULT 0,
    material_candidate INTEGER NOT NULL DEFAULT 0,
    material_candidate_reason TEXT,
    classification_source TEXT DEFAULT 'NONE',
    companies_json TEXT,
    stock_codes_json TEXT,
    numbers_json TEXT,
    original_source_id TEXT,
    original_source_name TEXT,
    article_count INTEGER NOT NULL DEFAULT 0,
    source_count INTEGER NOT NULL DEFAULT 0,
    confirmation_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT,
    last_seen_at TEXT,
    market_date TEXT,
    extraction_confidence REAL NOT NULL DEFAULT 0,
    extraction_version TEXT NOT NULL,
    cluster_updated_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_material_events_market_date
ON material_events(market_date);
CREATE INDEX IF NOT EXISTS idx_material_events_type
ON material_events(event_type);
CREATE INDEX IF NOT EXISTS idx_material_events_cluster
ON material_events(cluster_id);

CREATE TABLE IF NOT EXISTS event_families (
    family_id TEXT PRIMARY KEY,
    root_event_id TEXT NOT NULL,
    latest_event_id TEXT NOT NULL,
    primary_company TEXT,
    primary_ticker TEXT,
    event_type TEXT NOT NULL,
    first_seen_at TEXT,
    last_seen_at TEXT,
    event_count INTEGER NOT NULL DEFAULT 0,
    family_status TEXT NOT NULL DEFAULT 'ACTIVE',
    analysis_version TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_event_families_type
ON event_families(event_type);
CREATE INDEX IF NOT EXISTS idx_event_families_ticker
ON event_families(primary_ticker);
CREATE INDEX IF NOT EXISTS idx_event_families_last_seen
ON event_families(last_seen_at);

CREATE TABLE IF NOT EXISTS event_novelty (
    event_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    parent_event_id TEXT,
    novelty_status TEXT NOT NULL,
    novelty_score REAL NOT NULL DEFAULT 0,
    relation_score REAL NOT NULL DEFAULT 0,
    days_since_parent INTEGER,
    stage_changed INTEGER NOT NULL DEFAULT 0,
    stage_progressed INTEGER NOT NULL DEFAULT 0,
    number_changed INTEGER NOT NULL DEFAULT 0,
    company_changed INTEGER NOT NULL DEFAULT 0,
    polarity_changed INTEGER NOT NULL DEFAULT 0,
    source_reliability_increased INTEGER NOT NULL DEFAULT 0,
    confirmation_source_added INTEGER NOT NULL DEFAULT 0,
    new_information_count INTEGER NOT NULL DEFAULT 0,
    previous_stage TEXT,
    current_stage TEXT,
    previous_numbers_json TEXT,
    current_numbers_json TEXT,
    novelty_reason TEXT,
    analysis_version TEXT NOT NULL,
    event_updated_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_event_novelty_family
ON event_novelty(family_id);
CREATE INDEX IF NOT EXISTS idx_event_novelty_status
ON event_novelty(novelty_status);
CREATE INDEX IF NOT EXISTS idx_event_novelty_parent
ON event_novelty(parent_event_id);
"""


MIGRATION_COLUMNS = {
    "external_id": "TEXT",
    "published_at_precision": "TEXT DEFAULT 'UNKNOWN'",
    "first_seen_at": "TEXT",
    "last_seen_at": "TEXT",
}

MATERIAL_EVENT_MIGRATION_COLUMNS = {
    "material_candidate": "INTEGER NOT NULL DEFAULT 0",
    "material_candidate_reason": "TEXT",
    "classification_source": "TEXT DEFAULT 'NONE'",
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_material_events_candidate ON material_events(material_candidate)")

    @staticmethod
    def _migrate_columns(conn: sqlite3.Connection):
        existing = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
        for column, definition in MIGRATION_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE articles ADD COLUMN {column} {definition}")

        event_existing = {row[1] for row in conn.execute("PRAGMA table_info(material_events)")}
        for column, definition in MATERIAL_EVENT_MIGRATION_COLUMNS.items():
            if column not in event_existing:
                conn.execute(f"ALTER TABLE material_events ADD COLUMN {column} {definition}")

        conn.execute(
            "UPDATE articles SET external_id = CASE "
            "WHEN external_id IS NOT NULL AND external_id <> '' THEN external_id "
            "WHEN substr(article_id, 1, length(source_id) + 1) = source_id || '_' "
            "THEN substr(article_id, length(source_id) + 2) "
            "ELSE external_id END"
        )
        conn.execute(
            "UPDATE articles SET first_seen_at = COALESCE(first_seen_at, collected_at), "
            "last_seen_at = COALESCE(last_seen_at, collected_at)"
        )
