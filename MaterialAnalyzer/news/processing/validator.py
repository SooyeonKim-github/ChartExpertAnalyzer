from __future__ import annotations

from ..models import RawArticle


class ArticleValidator:
    def validate(self, article: RawArticle) -> tuple[bool, str | None]:
        if not article.article_id:
            return False, "EMPTY_ARTICLE_ID"
        if not article.source_id:
            return False, "EMPTY_SOURCE_ID"
        if not article.title.strip():
            return False, "EMPTY_TITLE"
        if not article.url.strip():
            return False, "EMPTY_URL"
        return True, None
