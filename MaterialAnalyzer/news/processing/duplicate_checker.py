from __future__ import annotations

from ..models import RawArticle


class ExactDuplicateChecker:
    def __init__(self, repository):
        self.repository = repository

    def find_exact(self, article: RawArticle):
        if article.url_hash:
            found = self.repository.find_by_url_hash(article.url_hash)
            if found:
                return found
        if article.content_hash:
            found = self.repository.find_by_content_hash(article.content_hash)
            if found:
                return found
        return None
