from __future__ import annotations

from dataclasses import dataclass

from ..models import RawArticle


@dataclass
class DuplicateMatch:
    article_id: str
    source_id: str
    match_type: str


class ExactDuplicateChecker:
    def __init__(self, repository):
        self.repository = repository

    def find_exact(self, article: RawArticle):
        if article.url_hash:
            found = self.repository.find_by_url_hash(article.url_hash)
            if found:
                return DuplicateMatch(found["article_id"], found["source_id"], "URL")
        if article.content_hash:
            found = self.repository.find_by_content_hash(article.content_hash)
            if found:
                return DuplicateMatch(found["article_id"], found["source_id"], "CONTENT")
        return None
