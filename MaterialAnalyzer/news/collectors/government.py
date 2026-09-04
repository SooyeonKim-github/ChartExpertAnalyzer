from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..exceptions import DiscoverError, ParseError
from ..models import ArticleCandidate, RawArticle
from .base import BaseCollector
from .factory import CollectorFactory


KST = ZoneInfo("Asia/Seoul")
DATE_RE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")

LINK_RULES = {
    "MOTIR": re.compile(r"/kor/article/ATCL3f49a5a8c/\d+/view(?:$|[?#])"),
    "MSIT": re.compile(r"/bbs/view\.do(?:$|[?#])"),
    "MCEE": re.compile(r"/home/web/newsRead\.do(?:$|[?#])"),
    "MFDS": re.compile(r"/brd/(?:m_)?99/view\.do(?:$|[?#])"),
    "FSC": re.compile(r"/no010101/\d+(?:$|[?#])"),
}

DETAIL_SELECTORS = {
    "MOTIR": [".article-view-content", ".view-cont", ".view_con", ".board-view", "#content"],
    "MSIT": [".view_cont", ".view-content", ".bbsView", ".board_view", "#content"],
    "MCEE": [".view_cont", ".view-content", ".news_view", ".board_view", "#content"],
    "MFDS": [".board_view", ".view_cont", ".view-content", ".bbs_view", "#content"],
    "FSC": [".view-content", ".board-view", ".board_view", ".contents", "#content"],
}


def _clean_text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _parse_date(text: str):
    match = DATE_RE.search(text or "")
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=KST)
    except ValueError:
        return None


def _external_id(source_id: str, url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if source_id == "MOTIR":
        match = re.search(r"/([0-9]+)/view", parsed.path)
        if match:
            return match.group(1)
    if source_id == "MSIT":
        return (query.get("nttSeqNo") or [""])[0]
    if source_id == "MCEE":
        return (query.get("boardId") or [""])[0]
    if source_id == "MFDS":
        return (query.get("seq") or [""])[0]
    if source_id == "FSC":
        match = re.search(r"/no010101/([0-9]+)", parsed.path)
        if match:
            return match.group(1)
    return ""


def _nearest_date(anchor):
    node = anchor
    for _ in range(5):
        if node is None:
            break
        parsed = _parse_date(_clean_text(node))
        if parsed:
            return parsed
        node = node.parent
    return None


def _looks_like_attachment(title: str, href: str) -> bool:
    combined = f"{title} {href}".lower()
    return any(ext in combined for ext in (".pdf", ".hwp", ".hwpx", ".xlsx", ".zip", "다운로드", "파일뷰어"))


def _extract_body(soup: BeautifulSoup, source_id: str, title: str) -> str | None:
    for selector in DETAIL_SELECTORS.get(source_id, []):
        node = soup.select_one(selector)
        text = _clean_text(node)
        if len(text) >= 120:
            return text

    title_node = None
    if title:
        for node in soup.find_all(["h1", "h2", "h3", "h4", "strong", "p", "div", "span"]):
            text = _clean_text(node)
            if text and (text == title or (len(title) >= 15 and title in text)):
                title_node = node
                break
    if title_node is not None:
        node = title_node
        candidates = []
        for _ in range(5):
            node = node.parent
            if node is None:
                break
            text = _clean_text(node)
            if 200 <= len(text) <= 50000:
                candidates.append(text)
        if candidates:
            return min(candidates, key=len)

    main = soup.find("main") or soup.find("article")
    text = _clean_text(main)
    if len(text) >= 120:
        return text
    return None


@CollectorFactory.register("GOV_HTML", "GOV_HTML_LIST")
class GovernmentCollector(BaseCollector):
    """Resilient collector for Korean government press-release boards.

    Discovery is based on stable detail-URL patterns rather than brittle CSS class names.
    """

    def discover(self):
        if not self.endpoint.list_url:
            raise DiscoverError(f"list_url is empty: {self.endpoint.endpoint_id}")
        rule = LINK_RULES.get(self.endpoint.source_id)
        if rule is None:
            raise DiscoverError(f"no government link rule: {self.endpoint.source_id}")

        fetched = self.http.get(self.endpoint.list_url)
        soup = BeautifulSoup(fetched.text or "", "html.parser")
        candidates = []
        seen = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            absolute = urljoin(self.endpoint.list_url, href)
            parsed = urlparse(absolute)
            path_query = parsed.path + ("?" + parsed.query if parsed.query else "")
            if not rule.search(path_query):
                continue
            title = _clean_text(anchor)
            if len(title) < 4 or _looks_like_attachment(title, href):
                continue
            if self.endpoint.source_id == "MSIT" and "bbsSeqNo=94" not in absolute:
                continue
            external_id = _external_id(self.endpoint.source_id, absolute)
            key = external_id or absolute
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                ArticleCandidate(
                    source_id=self.endpoint.source_id,
                    endpoint_id=self.endpoint.endpoint_id,
                    url=absolute,
                    external_id=external_id or None,
                    title_hint=title,
                    published_at_hint=_nearest_date(anchor),
                    category_hint=self.endpoint.category or self.endpoint.target_section,
                    metadata={"discovery_url": self.endpoint.list_url},
                )
            )
        if not candidates:
            raise DiscoverError(f"no press-release links discovered: {self.endpoint.endpoint_id}")
        return candidates

    def fetch(self, candidate):
        return self.http.get(candidate.url)

    def parse(self, candidate, fetched):
        soup = BeautifulSoup(fetched.text or "", "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = (candidate.title_hint or "").strip()
        if not title:
            heading = soup.find(["h1", "h2", "h3"])
            title = _clean_text(heading)
        if not title:
            raise ParseError(f"empty title: {candidate.url}")

        page_text = _clean_text(soup)
        published_at = candidate.published_at_hint or _parse_date(page_text)
        body = _extract_body(soup, self.endpoint.source_id, title)
        now = datetime.now(KST)
        external_id = candidate.external_id or hashlib.sha256(candidate.url.encode("utf-8")).hexdigest()[:16]
        return RawArticle(
            article_id=f"{self.endpoint.source_id}_{external_id}",
            source_id=self.endpoint.source_id,
            endpoint_id=self.endpoint.endpoint_id,
            source_name=self.endpoint.source_name,
            source_type=self.endpoint.source_type,
            source_grade=self.endpoint.source_grade,
            title=title,
            body=body,
            summary=candidate.summary_hint,
            url=candidate.url,
            canonical_url=candidate.url,
            author=None,
            published_at=published_at,
            updated_at=None,
            collected_at=now,
            published_date=published_at.date().isoformat() if published_at else None,
            market_date=None,
            category=candidate.category_hint,
            language="ko",
            article_class="PRESS_RELEASE",
            collector_type=self.endpoint.collector_type,
            content_mode=self.endpoint.content_mode,
            published_at_precision="DATE" if published_at else "UNKNOWN",
            body_length=len(body or ""),
            has_full_body=bool(body),
            http_status=fetched.status_code,
            source_metadata={**candidate.metadata, "external_id": candidate.external_id or ""},
        )
