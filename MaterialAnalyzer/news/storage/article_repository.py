from __future__ import annotations

import json
from datetime import datetime

from ..models import ArticleCandidate, RawArticle
from .database import Database


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


class ArticleRepository:
    COLUMNS = ["article_id","source_id","endpoint_id","source_name","source_type","source_grade","title","body","summary","url","canonical_url","author","published_at","updated_at","collected_at","published_date","market_date","category","language","article_class","collector_type","content_mode","url_hash","title_hash","content_hash","duplicate_of","body_length","has_full_body","fetch_status","http_status","parse_status","error_code","material_candidate","analysis_status","processed_at","source_metadata_json"]

    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()

    def exists_candidate(self, candidate: ArticleCandidate) -> bool:
        if candidate.external_id:
            return self.exists_article_id(f"{candidate.source_id}_{candidate.external_id}")
        return False

    def exists_article_id(self, article_id: str) -> bool:
        with self.database.connect() as conn:
            row = conn.execute("SELECT 1 FROM articles WHERE article_id = ? LIMIT 1", (article_id,)).fetchone()
        return row is not None

    def find_by_url_hash(self, url_hash: str):
        return self._find_one("url_hash", url_hash)

    def find_by_content_hash(self, content_hash: str):
        return self._find_one("content_hash", content_hash)

    def _find_one(self, column: str, value: str):
        if column not in {"url_hash", "content_hash"}:
            raise ValueError("unsupported lookup column")
        with self.database.connect() as conn:
            return conn.execute(f"SELECT article_id, url, title FROM articles WHERE {column} = ? LIMIT 1", (value,)).fetchone()

    def upsert(self, article: RawArticle) -> str:
        values = article.as_dict()
        for key in ("published_at", "updated_at", "collected_at", "processed_at"):
            values[key] = _iso(values[key])
        values["has_full_body"] = int(bool(values["has_full_body"]))
        values["material_candidate"] = int(bool(values["material_candidate"]))
        values["source_metadata_json"] = json.dumps(values.pop("source_metadata", {}), ensure_ascii=False, sort_keys=True)
        columns = self.COLUMNS
        placeholders = ",".join("?" for _ in columns)
        assignments = ",".join(f"{c}=excluded.{c}" for c in columns if c != "article_id")
        params = [values.get(c) for c in columns]
        with self.database.connect() as conn:
            existed = conn.execute("SELECT 1 FROM articles WHERE article_id = ?", (article.article_id,)).fetchone() is not None
            conn.execute(f"INSERT INTO articles ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT(article_id) DO UPDATE SET {assignments}, updated_db_at=CURRENT_TIMESTAMP", params)
        return "UPDATED" if existed else "INSERTED"
