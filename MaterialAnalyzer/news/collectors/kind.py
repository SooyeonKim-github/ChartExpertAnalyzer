from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..exceptions import DiscoverError
from ..models import ArticleCandidate, FetchedContent, RawArticle
from .base import BaseCollector
from .factory import CollectorFactory


KST = ZoneInfo("Asia/Seoul")
ACPT_RE = re.compile(r"(?<!\d)(20\d{12})(?!\d)")
TIME_RE = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")


@CollectorFactory.register("KIND_HTML", "KIND")
class KindCollector(BaseCollector):
    """KRX KIND today's-disclosure collector using public KOSPI/KOSDAQ screens."""

    MARKET_TYPES = ("1", "2")

    def discover(self):
        now = datetime.now(KST)
        candidates = []
        seen = set()

        for market_type in self.MARKET_TYPES:
            params = {
                "method": "searchTodayDisclosureMain",
                "marketType": market_type,
            }
            fetched = self.http.get(self.endpoint.list_url, params=params)
            soup = BeautifulSoup(fetched.text or "", "html.parser")
            page_url = fetched.url

            for row in soup.select("table tr"):
                row_text = row.get_text(" ", strip=True)
                time_match = TIME_RE.search(row_text)
                if not row_text or not time_match:
                    continue

                cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
                if len(cells) < 3:
                    continue

                company = cells[1].strip()
                report_title = cells[2].strip()
                if len(report_title) < 4:
                    continue

                row_html = str(row)
                acpt_match = ACPT_RE.search(row_html)
                acptno = acpt_match.group(1) if acpt_match else ""

                published_at = now.replace(
                    hour=int(time_match.group(1)),
                    minute=int(time_match.group(2)),
                    second=0,
                    microsecond=0,
                )

                if acptno:
                    external_id = acptno
                    viewer_url = (
                        "https://kind.krx.co.kr/common/disclsviewer.do"
                        f"?method=search&acptno={acptno}&docno=&viewerhost=&viewerport="
                    )
                else:
                    stable = (
                        f"{now:%Y%m%d}|{market_type}|{time_match.group(0)}|"
                        f"{company}|{report_title}"
                    )
                    external_id = "ROW_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
                    viewer_url = (
                        self.endpoint.list_url
                        + "?"
                        + urlencode(
                            {
                                "method": "searchTodayDisclosureMain",
                                "marketType": market_type,
                                "rowKey": external_id,
                            }
                        )
                    )

                if external_id in seen:
                    continue
                seen.add(external_id)

                candidates.append(
                    ArticleCandidate(
                        source_id=self.endpoint.source_id,
                        endpoint_id=self.endpoint.endpoint_id,
                        url=viewer_url,
                        external_id=external_id,
                        title_hint=report_title,
                        published_at_hint=published_at,
                        category_hint="DISCLOSURE",
                        metadata={
                            "acptno": acptno,
                            "company_name": company,
                            "row_text": row_text,
                            "market_type": market_type,
                            "discovery_url": page_url,
                        },
                    )
                )

        if not candidates:
            raise DiscoverError(
                "KIND returned no KOSPI/KOSDAQ disclosure rows from the public main screens"
            )
        return candidates

    def fetch(self, candidate):
        return FetchedContent(
            url=candidate.url,
            status_code=200,
            content_type="application/vnd.krx.kind.metadata+json",
            text=None,
            raw_bytes=None,
            fetched_at=datetime.now(KST),
            encoding="utf-8",
        )

    def parse(self, candidate, fetched):
        now = datetime.now(KST)
        title = (candidate.title_hint or "").strip()
        company = candidate.metadata.get("company_name", "")
        return RawArticle(
            article_id=f"KIND_{candidate.external_id}",
            source_id=self.endpoint.source_id,
            endpoint_id=self.endpoint.endpoint_id,
            source_name=self.endpoint.source_name,
            source_type=self.endpoint.source_type,
            source_grade=self.endpoint.source_grade,
            title=title,
            body=None,
            summary=None,
            url=candidate.url,
            canonical_url=candidate.url,
            author=company or None,
            published_at=candidate.published_at_hint,
            updated_at=None,
            collected_at=now,
            published_date=candidate.published_at_hint.date().isoformat()
            if candidate.published_at_hint
            else now.date().isoformat(),
            market_date=None,
            category="DISCLOSURE",
            language="ko",
            article_class="DISCLOSURE",
            collector_type=self.endpoint.collector_type,
            content_mode="DISCOVERY",
            published_at_precision="MINUTE" if candidate.published_at_hint else "DATE",
            body_length=0,
            has_full_body=False,
            http_status=200,
            source_metadata=candidate.metadata,
        )
