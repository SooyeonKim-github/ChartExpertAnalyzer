from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import requests

from ..config import MaterialCollectorConfig
from ..models import CollectedItem, clean_text


class NaverNewsCollector:
    source_name = "naver_news"

    def __init__(self, config: MaterialCollectorConfig) -> None:
        self.config = config

    def available(self) -> bool:
        client_id, client_secret = self.config.naver_credentials()
        return bool(client_id and client_secret)

    def collect(self, queries: Iterable[tuple[str, str]], collected_at: str) -> list[CollectedItem]:
        client_id, client_secret = self.config.naver_credentials()
        if not client_id or not client_secret:
            return []

        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "User-Agent": self.config.user_agent,
        }
        out: list[CollectedItem] = []

        for category, query in queries:
            start = 1
            for _ in range(self.config.naver_max_pages_per_query):
                params = {
                    "query": query,
                    "display": self.config.naver_display,
                    "start": start,
                    "sort": "date",
                }
                response = requests.get(
                    self.config.naver_news_api_url,
                    params=params,
                    headers=headers,
                    timeout=self.config.request_timeout_sec,
                )
                response.raise_for_status()
                payload = response.json()
                items = payload.get("items") or []
                if not items:
                    break

                for raw in items:
                    title = clean_text(raw.get("title"))
                    summary = clean_text(raw.get("description"))
                    link = raw.get("originallink") or raw.get("link") or ""
                    published_at = self._parse_pub_date(raw.get("pubDate"))
                    haystack = f"{title} {summary}"
                    future_hint = any(k in haystack for k in self.config.future_hint_keywords)
                    out.append(
                        CollectedItem(
                            collected_at=collected_at,
                            published_at=published_at,
                            source_type="news",
                            source=self.source_name,
                            title=title,
                            summary=summary,
                            url=link,
                            query=query,
                            category=category,
                            future_hint=future_hint,
                        )
                    )

                if len(items) < self.config.naver_display:
                    break
                start += self.config.naver_display
                if start > 1000:
                    break

        return out

    @staticmethod
    def _parse_pub_date(value: str | None) -> str:
        if not value:
            return ""
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (TypeError, ValueError, OverflowError):
            return str(value)
