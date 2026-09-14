from __future__ import annotations

from datetime import datetime, timedelta

from ..storage import Database
from .models import AnalyzerStats
from .rule_classifier import RuleClassifier


_EXCLUDED_ARTICLE_CLASSES = {"DISCLOSURE", "MARKET_REACTION"}
_EXCLUDED_SOURCE_IDS = {"DART", "KIND"}


class ThemeSectorAnalyzer:
    """Analyze ArticleCluster representatives without linking to individual tickers."""

    VERSION = "THEME_SECTOR_ANALYZER_V1_2"

    def __init__(self, database: Database, classifier: RuleClassifier):
        self.database = database
        self.database.initialize()
        self.classifier = classifier

    def run(
        self,
        *,
        end_date: str | None = None,
        days: int = 7,
        limit: int | None = None,
        include_sector_only: bool = False,
    ) -> tuple[AnalyzerStats, list[dict]]:
        if days < 1:
            raise ValueError("days must be >= 1")

        resolved_end = end_date or self._latest_market_date()
        if not resolved_end:
            return AnalyzerStats(start_date="", end_date=""), []
        _validate_market_date(resolved_end)
        resolved_start = (
            datetime.strptime(resolved_end, "%Y%m%d") - timedelta(days=days - 1)
        ).strftime("%Y%m%d")

        cluster_rows = self._load_clusters(resolved_start, resolved_end, limit=limit)
        stats = AnalyzerStats(start_date=resolved_start, end_date=resolved_end)
        output_rows: list[dict] = []

        for row in cluster_rows:
            stats.clusters_scanned += 1
            article_class = str(row["article_class"] or "").upper()
            source_id = str(row["source_id"] or "").upper()
            if article_class in _EXCLUDED_ARTICLE_CLASSES or source_id in _EXCLUDED_SOURCE_IDS:
                continue

            result = self.classifier.classify(
                title=row["title"],
                summary=row["summary"],
                body=row["body"],
            )

            if result.themes:
                stats.clusters_with_theme += 1
                stats.theme_matches += len(result.themes)
                for theme in result.themes:
                    output_rows.append(self._theme_record(row, theme))
            elif result.sectors:
                stats.sector_only_clusters += 1
                if include_sector_only:
                    for sector in result.sectors:
                        output_rows.append(self._sector_only_record(row, sector))

        output_rows.sort(
            key=lambda r: (
                r.get("market_date") or "",
                float(r.get("rule_score") or 0),
                float(r.get("confidence") or 0),
            ),
            reverse=True,
        )
        return stats, output_rows

    def _latest_market_date(self) -> str | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT MAX(market_date) AS market_date "
                "FROM article_clusters WHERE cluster_status='ACTIVE' "
                "AND market_date IS NOT NULL AND market_date <> ''"
            ).fetchone()
        return str(row["market_date"]) if row and row["market_date"] else None

    def _load_clusters(self, start_date: str, end_date: str, *, limit: int | None):
        sql = (
            "SELECT c.cluster_id, c.cluster_title, c.market_date, c.article_count, "
            "c.source_count, c.confirmation_count, c.cluster_confidence, "
            "c.first_seen_at AS cluster_first_seen_at, "
            "c.last_seen_at AS cluster_last_seen_at, "
            "a.article_id, a.title, a.summary, a.body, a.url, a.source_id, "
            "a.source_name, a.source_grade, a.article_class, a.published_at "
            "FROM article_clusters c "
            "JOIN articles a ON a.article_id = c.representative_article_id "
            "WHERE c.cluster_status='ACTIVE' AND c.market_date BETWEEN ? AND ? "
            "ORDER BY c.market_date DESC, c.last_seen_at DESC, c.cluster_id"
        )
        params: list[object] = [start_date, end_date]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    @staticmethod
    def _base_record(row) -> dict:
        return {
            "market_date": row["market_date"],
            "cluster_id": row["cluster_id"],
            "cluster_title": row["cluster_title"],
            "representative_article_id": row["article_id"],
            "representative_title": row["title"],
            "article_count": row["article_count"],
            "source_count": row["source_count"],
            "confirmation_count": row["confirmation_count"],
            "cluster_confidence": row["cluster_confidence"],
            "first_seen_at": row["cluster_first_seen_at"],
            "last_seen_at": row["cluster_last_seen_at"],
            "published_at": row["published_at"],
            "source_id": row["source_id"],
            "source_name": row["source_name"],
            "source_grade": row["source_grade"],
            "article_class": row["article_class"],
            "url": row["url"],
            "analyzer_version": ThemeSectorAnalyzer.VERSION,
            "classifier_version": RuleClassifier.VERSION,
        }

    def _theme_record(self, row, theme) -> dict:
        record = self._base_record(row)
        record.update(
            {
                "classification_type": "THEME",
                "theme_family": theme.theme_family,
                "theme_family_name_ko": theme.theme_family_name_ko,
                "theme": theme.theme,
                "theme_name_ko": theme.theme_name_ko,
                "theme_description": theme.description,
                "sectors": "|".join(theme.sectors),
                "sector_names_ko": "|".join(theme.sector_names_ko),
                "subsectors": "|".join(theme.subsectors),
                "subsector_names_ko": "|".join(theme.subsector_names_ko),
                "direction": theme.direction,
                "rule_score": theme.rule_score,
                "confidence": theme.confidence,
                "matched_keywords": "|".join(theme.matched_keywords),
                "positive_hits": "|".join(theme.positive_hits),
                "negative_hits": "|".join(theme.negative_hits),
            }
        )
        return record

    def _sector_only_record(self, row, sector) -> dict:
        record = self._base_record(row)
        record.update(
            {
                "classification_type": "SECTOR_ONLY",
                "theme_family": "",
                "theme_family_name_ko": "",
                "theme": "",
                "theme_name_ko": "",
                "theme_description": "",
                "sectors": sector.sector,
                "sector_names_ko": sector.sector_name_ko,
                "subsectors": "|".join(sector.subsectors),
                "subsector_names_ko": "|".join(sector.subsector_names_ko),
                "direction": "NEUTRAL",
                "rule_score": sector.score,
                "confidence": "",
                "matched_keywords": "|".join(sector.matched_keywords),
                "positive_hits": "",
                "negative_hits": "",
            }
        )
        return record


def _validate_market_date(value: str) -> None:
    if len(value) != 8 or not value.isdigit():
        raise ValueError("market date must be YYYYMMDD")
    datetime.strptime(value, "%Y%m%d")
