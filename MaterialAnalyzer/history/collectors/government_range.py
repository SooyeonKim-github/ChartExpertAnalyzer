from __future__ import annotations

from dataclasses import replace
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from MaterialAnalyzer.news.collectors.government import GovernmentCollector
from MaterialAnalyzer.news.exceptions import DiscoverError


PAGE_RULES = {
    "MOTIR": ("pageIndex", lambda page: str(page)),
    "MSIT": ("pageIndex", lambda page: str(page)),
    "MCEE": ("pagerOffset", lambda page: str((page - 1) * 10)),
    "MFDS": ("page", lambda page: str(page)),
    "FSC": ("curPage", lambda page: str(page)),
}


def _page_url(url: str, source_id: str, page: int) -> str:
    rule = PAGE_RULES.get(source_id)
    if not rule or page <= 1:
        return url
    param, value_factory = rule
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query[param] = value_factory(page)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


class GovernmentRangeCollector:
    """Best-effort historical traversal of enabled official press-release boards.

    Only candidates whose list row exposes a publication date are accepted. This is
    intentional: an undated historical row must not be assigned today's collection
    timestamp and leak into a point-in-time backtest.
    """

    def __init__(self, endpoint, start_date: date, end_date: date, *, max_pages: int = 500):
        self.endpoint = endpoint
        self.start_date = start_date
        self.end_date = end_date
        self.max_pages = max(1, int(max_pages))
        self._parser = GovernmentCollector(endpoint)

    def discover(self):
        if self.endpoint.source_id not in PAGE_RULES:
            raise DiscoverError(f"historical pagination rule is not configured: {self.endpoint.source_id}")
        accepted = []
        seen = set()
        previous_signature = None

        for page in range(1, self.max_pages + 1):
            paged = replace(
                self.endpoint,
                list_url=_page_url(self.endpoint.list_url, self.endpoint.source_id, page),
                rss_url="",
            )
            try:
                rows = GovernmentCollector(paged, self._parser.http).discover()
            except Exception:
                if page == 1:
                    raise
                break
            signature = tuple(sorted((row.external_id or row.url) for row in rows))
            if signature == previous_signature:
                break
            previous_signature = signature

            dated = [row for row in rows if row.published_at_hint is not None]
            if not dated:
                # Do not guess dates in historical mode.
                continue

            oldest = min(row.published_at_hint.date() for row in dated)
            for row in dated:
                published = row.published_at_hint.date()
                if not (self.start_date <= published <= self.end_date):
                    continue
                key = row.external_id or row.url
                if key in seen:
                    continue
                seen.add(key)
                row.metadata = {**row.metadata, "historical_range": True, "historical_page": page, "date_only": True}
                accepted.append(row)

            if oldest < self.start_date:
                break
        return accepted

    def fetch(self, candidate):
        return self._parser.fetch(candidate)

    def parse(self, candidate, fetched):
        article = self._parser.parse(candidate, fetched)
        article.source_metadata = {**article.source_metadata, "historical_range": True, "date_only": True}
        return article
