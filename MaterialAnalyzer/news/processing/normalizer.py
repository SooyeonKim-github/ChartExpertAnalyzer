from __future__ import annotations

from ..models import RawArticle


class PassThroughNormalizer:
    """Temporary V1 normalizer. Production ArticleNormalizer is the next step."""

    def normalize(self, article: RawArticle) -> RawArticle:
        return article
