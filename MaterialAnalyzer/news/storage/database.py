from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
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
"""


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
