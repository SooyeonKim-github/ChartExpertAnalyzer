from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from ..exceptions import DiscoverError
from ..models import ArticleCandidate, FetchedContent, RawArticle
from .base import BaseCollector
from .factory import CollectorFactory


def _first_text(node, names):
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _parse_rss_date(value: str):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


@CollectorFactory.register("RSS", "GOV_RSS")
class RSSCollector(BaseCollector):
    def discover(self):
        rss_url = self.endpoint.rss_url or self.endpoint.list_url
        if not rss_url:
            raise DiscoverError(f"rss_url is empty: {self.endpoint.endpoint_id}")
        fetched = self.http.get(rss_url)
        root = ET.fromstring(fetched.text or "")
        candidates = []
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items:
            title = _first_text(item, ["title", "{http://www.w3.org/2005/Atom}title"])
            link = _first_text(item, ["link"])
            if not link:
                atom_link = item.find("{http://www.w3.org/2005/Atom}link")
                if atom_link is not None:
                    link = atom_link.attrib.get("href", "")
            date_text = _first_text(item, ["pubDate", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"])
            summary = _first_text(item, ["description", "{http://www.w3.org/2005/Atom}summary"])
            if title and link:
                candidates.append(ArticleCandidate(source_id=self.endpoint.source_id, endpoint_id=self.endpoint.endpoint_id, url=urljoin(rss_url, link), title_hint=title, published_at_hint=_parse_rss_date(date_text), summary_hint=summary or None, category_hint=self.endpoint.category or self.endpoint.target_section))
        return candidates

    def fetch(self, candidate):
        if self.endpoint.content_mode.upper() == "DISCOVERY":
            return FetchedContent(url=candidate.url, status_code=200, content_type="application/rss+xml", text="", fetched_at=datetime.now(timezone.utc))
        return self.http.get(candidate.url)

    def parse(self, candidate, fetched):
        body = None
        if fetched.text and self.endpoint.body_selector:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(fetched.text, "html.parser")
            node = soup.select_one(self.endpoint.body_selector)
            body = node.get_text(" ", strip=True) if node else None
        now = datetime.now(timezone.utc)
        digest = hashlib.sha256(candidate.url.encode("utf-8")).hexdigest()[:12]
        return RawArticle(article_id=f"{self.endpoint.source_id}_{digest}", source_id=self.endpoint.source_id, endpoint_id=self.endpoint.endpoint_id, source_name=self.endpoint.source_name, source_type=self.endpoint.source_type, source_grade=self.endpoint.source_grade, title=candidate.title_hint or "", body=body, summary=candidate.summary_hint, url=candidate.url, canonical_url=candidate.url, author=None, published_at=candidate.published_at_hint, updated_at=None, collected_at=now, published_date=candidate.published_at_hint.date().isoformat() if candidate.published_at_hint else None, market_date=None, category=candidate.category_hint, language="ko", article_class="PRESS_RELEASE" if self.endpoint.source_type == "GOV" else "UNKNOWN", collector_type=self.endpoint.collector_type, content_mode=self.endpoint.content_mode, body_length=len(body or ""), has_full_body=bool(body), http_status=fetched.status_code)
