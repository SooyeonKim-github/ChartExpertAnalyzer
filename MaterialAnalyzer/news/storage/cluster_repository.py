from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from ..clustering.event_key import build_event_key
from ..clustering.representative_selector import RepresentativeSelector
from .database import Database


class ClusterRepository:
    VERSION = "RULE_CLUSTER_V1"

    def __init__(self, database: Database, feature_extractor):
        self.database = database
        self.database.initialize()
        self.feature_extractor = feature_extractor
        self.representative_selector = RepresentativeSelector()

    def clear_all(self):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM article_cluster_members")
            conn.execute("DELETE FROM article_clusters")

    def get_unclustered_articles(self, limit: int | None = None):
        sql = (
            "SELECT a.* FROM articles a "
            "LEFT JOIN article_cluster_members m ON m.article_id = a.article_id "
            "WHERE m.article_id IS NULL "
            "ORDER BY COALESCE(a.first_seen_at, a.collected_at) ASC, a.article_id ASC"
        )
        params = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (int(limit),)
        with self.database.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def get_article(self, article_id: str):
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT * FROM articles WHERE article_id = ? LIMIT 1", (article_id,)
            ).fetchone()

    def find_cluster_by_external_id(self, external_id: str, source_ids: tuple[str, ...] = ("DART", "KIND")):
        if not external_id:
            return None
        placeholders = ",".join("?" for _ in source_ids)
        with self.database.connect() as conn:
            return conn.execute(
                f"SELECT m.cluster_id FROM article_cluster_members m "
                f"JOIN articles a ON a.article_id = m.article_id "
                f"WHERE a.external_id = ? AND a.source_id IN ({placeholders}) LIMIT 1",
                (external_id, *source_ids),
            ).fetchone()

    def candidate_representatives(self, market_dates: list[str]):
        if not market_dates:
            return []
        placeholders = ",".join("?" for _ in market_dates)
        with self.database.connect() as conn:
            return conn.execute(
                f"SELECT c.cluster_id, a.* FROM article_clusters c "
                f"JOIN articles a ON a.article_id = c.representative_article_id "
                f"WHERE c.cluster_status = 'ACTIVE' AND c.market_date IN ({placeholders}) "
                f"ORDER BY c.last_seen_at DESC",
                tuple(market_dates),
            ).fetchall()

    def create_cluster(self, article_row, features) -> str:
        digest = hashlib.sha256(article_row["article_id"].encode("utf-8")).hexdigest()[:16]
        cluster_id = f"CL_{digest}"
        event_key = build_event_key(features)
        first_seen = article_row["first_seen_at"] or article_row["collected_at"]
        last_seen = article_row["last_seen_at"] or article_row["collected_at"]
        with self.database.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO article_clusters("
                "cluster_id, representative_article_id, cluster_title, event_key, first_seen_at, "
                "last_seen_at, market_date, article_count, source_count, confirmation_count, "
                "cluster_confidence, cluster_status, clustering_version"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, 0, 100.0, 'ACTIVE', ?)",
                (
                    cluster_id,
                    article_row["article_id"],
                    article_row["title"],
                    event_key,
                    first_seen,
                    last_seen,
                    article_row["market_date"],
                    self.VERSION,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO article_cluster_members("
                "cluster_id, article_id, match_score, match_method, match_reason, is_representative"
                ") VALUES (?, ?, 100.0, 'NEW_CLUSTER', 'cluster seed', 1)",
                (cluster_id, article_row["article_id"]),
            )
        return cluster_id

    def add_member(self, cluster_id: str, article_id: str, score: float, method: str, reason: str):
        with self.database.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO article_cluster_members("
                "cluster_id, article_id, match_score, match_method, match_reason, is_representative"
                ") VALUES (?, ?, ?, ?, ?, 0)",
                (cluster_id, article_id, float(score), method, reason),
            )

    def refresh_cluster(self, cluster_id: str):
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT a.* FROM article_cluster_members m "
                "JOIN articles a ON a.article_id = m.article_id "
                "WHERE m.cluster_id = ?",
                (cluster_id,),
            ).fetchall()
        if not rows:
            return

        representative = self.representative_selector.choose(rows)
        rep_features = self.feature_extractor.extract(representative)

        first_seen = min(
            (row["first_seen_at"] or row["collected_at"] for row in rows if row["first_seen_at"] or row["collected_at"]),
            default=None,
        )
        last_seen = max(
            (row["last_seen_at"] or row["collected_at"] for row in rows if row["last_seen_at"] or row["collected_at"]),
            default=None,
        )
        source_count = len({row["source_id"] for row in rows})
        confirmation_sources = {
            row["source_id"] for row in rows if (row["article_class"] or "") != "MARKET_REACTION"
        }
        confirmation_count = max(0, len(confirmation_sources) - 1)

        with self.database.connect() as conn:
            score_rows = conn.execute(
                "SELECT match_score FROM article_cluster_members "
                "WHERE cluster_id = ? AND match_method <> 'NEW_CLUSTER'",
                (cluster_id,),
            ).fetchall()
            confidence = (
                round(sum(float(r["match_score"] or 0) for r in score_rows) / len(score_rows), 2)
                if score_rows
                else 100.0
            )
            conn.execute(
                "UPDATE article_cluster_members SET is_representative = "
                "CASE WHEN article_id = ? THEN 1 ELSE 0 END WHERE cluster_id = ?",
                (representative["article_id"], cluster_id),
            )
            conn.execute(
                "UPDATE article_clusters SET representative_article_id=?, cluster_title=?, event_key=?, "
                "first_seen_at=?, last_seen_at=?, market_date=?, article_count=?, source_count=?, "
                "confirmation_count=?, cluster_confidence=?, clustering_version=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE cluster_id=?",
                (
                    representative["article_id"],
                    representative["title"],
                    build_event_key(rep_features),
                    first_seen,
                    last_seen,
                    representative["market_date"],
                    len(rows),
                    source_count,
                    confirmation_count,
                    confidence,
                    self.VERSION,
                    cluster_id,
                ),
            )

    def cluster_count(self) -> int:
        with self.database.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM article_clusters").fetchone()
            return int(row["cnt"])

    def multi_member_count(self) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM article_clusters WHERE article_count > 1"
            ).fetchone()
            return int(row["cnt"])

    def export_report(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT c.cluster_id, c.cluster_title, c.representative_article_id, c.event_key, "
                "c.article_count, c.source_count, c.confirmation_count, c.cluster_confidence, "
                "c.first_seen_at AS cluster_first_seen_at, c.last_seen_at AS cluster_last_seen_at, "
                "m.match_score, m.match_method, m.match_reason, m.is_representative, "
                "a.article_id, a.source_id, a.source_name, a.source_type, a.source_grade, a.article_class, "
                "a.external_id, a.author, a.body, a.summary, a.market_date, a.published_at, "
                "a.first_seen_at, a.title, a.url, a.source_metadata_json "
                "FROM article_clusters c "
                "JOIN article_cluster_members m ON m.cluster_id = c.cluster_id "
                "JOIN articles a ON a.article_id = m.article_id "
                "ORDER BY c.article_count DESC, c.first_seen_at ASC, c.cluster_id, m.is_representative DESC"
            ).fetchall()

        fieldnames = [
            "cluster_id", "cluster_title", "representative_article_id", "event_key",
            "article_count", "source_count", "confirmation_count", "cluster_confidence",
            "cluster_first_seen_at", "cluster_last_seen_at", "article_id", "source_id",
            "source_name", "source_grade", "article_class", "market_date", "published_at",
            "first_seen_at", "title", "event_type", "companies", "stock_codes", "numbers",
            "match_score", "match_method", "match_reason", "is_representative", "url",
            "source_metadata_json",
        ]
        with output.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                features = self.feature_extractor.extract(row)
                record = {}
                for key in fieldnames:
                    if key == "event_type":
                        record[key] = features.event_type
                    elif key == "companies":
                        record[key] = "|".join(features.companies)
                    elif key == "stock_codes":
                        record[key] = "|".join(features.stock_codes)
                    elif key == "numbers":
                        record[key] = "|".join(features.numbers)
                    else:
                        record[key] = row[key]
                writer.writerow(record)
        return output
