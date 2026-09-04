from __future__ import annotations

from ..models import RawArticle
from .normalization import (
    MarketDateResolver,
    infer_published_precision,
    normalize_body,
    normalize_datetime,
    normalize_display_text,
    normalize_hash_text,
    normalize_url,
    sha256_text,
)


class ArticleNormalizer:
    """Normalize a source-specific RawArticle into stable storage/search fields."""

    def __init__(self, market_date_resolver: MarketDateResolver | None = None):
        self.market_date_resolver = market_date_resolver or MarketDateResolver()

    def normalize(self, article: RawArticle) -> RawArticle:
        article.url = (article.url or "").strip()
        article.canonical_url = normalize_url(article.canonical_url or article.url, article.source_id)

        article.title = normalize_display_text(article.title) or ""
        article.body = normalize_body(article.body)
        article.summary = normalize_display_text(article.summary)
        article.author = normalize_display_text(article.author)

        article.published_at = normalize_datetime(article.published_at)
        article.updated_at = normalize_datetime(article.updated_at)
        article.collected_at = normalize_datetime(article.collected_at) or article.collected_at
        article.first_seen_at = normalize_datetime(article.first_seen_at) or article.collected_at
        article.last_seen_at = normalize_datetime(article.last_seen_at) or article.collected_at

        article.published_at_precision = infer_published_precision(
            article.source_id,
            article.published_at,
            article.source_metadata,
        )
        article.published_date = article.published_at.date().isoformat() if article.published_at else None

        available_at = article.first_seen_at or article.collected_at or article.published_at
        article.market_date = self.market_date_resolver.resolve(available_at)

        article.url_hash = sha256_text(article.canonical_url or article.url)
        title_for_hash = normalize_hash_text(article.title)
        body_for_hash = normalize_hash_text(article.body)
        article.title_hash = sha256_text(title_for_hash)
        article.content_hash = sha256_text(body_for_hash or title_for_hash)

        article.body_length = len(article.body or "")
        article.has_full_body = bool(article.body)
        return article


class PassThroughNormalizer(ArticleNormalizer):
    """Backward-compatible alias kept for callers created before NewsCollector V1.1."""

    pass
