from __future__ import annotations

from MaterialAnalyzer.news.processing import ArticleNormalizer


class HistoricalArticleNormalizer(ArticleNormalizer):
    """Normalize backfilled articles without turning collection time into signal time."""

    def normalize(self, article):
        if article.published_at is not None:
            article.first_seen_at = article.published_at
            if article.last_seen_at is None:
                article.last_seen_at = article.published_at
        article = super().normalize(article)
        article.market_date = self.market_date_resolver.resolve_historical(
            article.published_at,
            article.published_at_precision,
        )
        return article
