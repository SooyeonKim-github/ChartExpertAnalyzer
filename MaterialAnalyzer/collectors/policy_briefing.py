from __future__ import annotations

from datetime import date, timedelta
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..config import MaterialCollectorConfig
from ..models import CollectedItem, clean_text


_DATE_RE = re.compile(r"20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}")


class PolicyBriefingCollector:
    source_name = "policy_briefing"

    def __init__(self, config: MaterialCollectorConfig) -> None:
        self.config = config

    def available(self) -> bool:
        return True

    def collect(self, end_date: date, days: int, collected_at: str) -> list[CollectedItem]:
        begin_date = end_date - timedelta(days=max(days - 1, 0))
        out: list[CollectedItem] = []
        seen_urls: set[str] = set()

        max_pages = max(1, (self.config.policy_max_items + 9) // 10)
        for page_index in range(1, max_pages + 1):
            response = requests.get(
                self.config.policy_briefing_url,
                params={
                    "startDate": begin_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "pageIndex": page_index,
                },
                headers={"User-Agent": self.config.user_agent},
                timeout=self.config.request_timeout_sec,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_added = 0

            for anchor in soup.find_all("a", href=True):
                href = str(anchor.get("href") or "")
                if "pressReleaseView.do" not in href:
                    continue

                url = urljoin(self.config.policy_briefing_url, href)
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = clean_text(anchor.get_text(" ", strip=True))
                if not title:
                    continue

                parent_text = clean_text(anchor.parent.get_text(" ", strip=True) if anchor.parent else "")
                date_match = _DATE_RE.search(parent_text)
                published_at = date_match.group(0) if date_match else ""
                if published_at:
                    parsed_day = self._parse_date(published_at)
                    if parsed_day and not (begin_date <= parsed_day <= end_date):
                        continue

                summary = parent_text
                if summary.startswith(title):
                    summary = summary[len(title):].strip()
                summary = summary[:1000]

                haystack = f"{title} {summary}"
                out.append(
                    CollectedItem(
                        collected_at=collected_at,
                        published_at=published_at,
                        source_type="policy",
                        source=self.source_name,
                        title=title,
                        summary=summary,
                        url=url,
                        category="press_release",
                        future_hint=any(k in haystack for k in self.config.future_hint_keywords),
                    )
                )
                page_added += 1
                if len(out) >= self.config.policy_max_items:
                    return out

            if page_added == 0:
                break

        return out

    @staticmethod
    def _parse_date(value: str) -> date | None:
        normalized = value.replace(".", "-").replace("/", "-")
        parts = normalized.split("-")
        if len(parts) != 3:
            return None
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
