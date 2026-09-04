from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..exceptions import DiscoverError, ParseError
from ..models import ArticleCandidate, RawArticle
from .base import BaseCollector
from .factory import CollectorFactory


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


@CollectorFactory.register("HTML_LIST", "NEWS_SECTION")
class HtmlListCollector(BaseCollector):
    def discover(self):
        if not self.endpoint.list_url:
            raise DiscoverError(f"list_url is empty: {self.endpoint.endpoint_id}")
        if not self.endpoint.item_selector:
            raise DiscoverError(f"item_selector is empty: {self.endpoint.endpoint_id}")
        fetched = self.http.get(self.endpoint.list_url)
        soup = BeautifulSoup(fetched.text or "", "html.parser")
        candidates = []
        for item in soup.select(self.endpoint.item_selector):
            title_node = item.select_one(self.endpoint.title_selector) if self.endpoint.title_selector else item
            link_node = item.select_one(self.endpoint.link_selector) if self.endpoint.link_selector else item.find("a")
            href = link_node.get("href") if link_node else None
            title = _text(title_node)
            if not href or not title:
                continue
            candidates.append(ArticleCandidate(source_id=self.endpoint.source_id, endpoint_id=self.endpoint.endpoint_id, url=urljoin(self.endpoint.list_url, href), title_hint=title, category_hint=self.endpoint.category or self.endpoint.target_section))
        return candidates

    def fetch(self, candidate):
        return self.http.get(candidate.url)

    def parse(self, candidate, fetched):
        soup = BeautifulSoup(fetched.text or "", "html.parser")
        title_node = soup.select_one(self.endpoint.title_selector) if self.endpoint.title_selector else None
        body_node = soup.select_one(self.endpoint.body_selector) if self.endpoint.body_selector else None
        author_node = soup.select_one(self.endpoint.author_selector) if self.endpoint.author_selector else None
        title = _text(title_node) or candidate.title_hint or ""
        body = _text(body_node) if body_node else None
        if not title:
            raise ParseError(f"empty title: {candidate.url}")
        now = datetime.now(timezone.utc)
        external_key = candidate.external_id or candidate.url
        digest = hashlib.sha256(external_key.encode("utf-8")).hexdigest()[:12]
        return RawArticle(article_id=f"{self.endpoint.source_id}_{digest}", source_id=self.endpoint.source_id, endpoint_id=self.endpoint.endpoint_id, source_name=self.endpoint.source_name, source_type=self.endpoint.source_type, source_grade=self.endpoint.source_grade, title=title, body=body, summary=candidate.summary_hint, url=candidate.url, canonical_url=candidate.url, author=_text(author_node) or None, published_at=candidate.published_at_hint, updated_at=None, collected_at=now, published_date=candidate.published_at_hint.date().isoformat() if candidate.published_at_hint else None, market_date=None, category=candidate.category_hint, language="ko", article_class="UNKNOWN", collector_type=self.endpoint.collector_type, content_mode=self.endpoint.content_mode, body_length=len(body or ""), has_full_body=bool(body), http_status=fetched.status_code, source_metadata=candidate.metadata)
