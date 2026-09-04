from __future__ import annotations

import re
from datetime import datetime
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
    """KRX KIND today's-disclosure collector using the official POST screen."""

    def discover(self):
        now = datetime.now(KST)
        payload = {
            "method": "searchTodayDisclosureSub",
            "currentPageSize": "100",
            "pageIndex": "1",
            "orderMode": "0",
            "orderStat": "D",
            "forward": "todaydisclosure_sub",
            "chose": "S",
            "todayFlag": "N",
            "marketType": "0",
            "selDate": now.strftime("%Y-%m-%d"),
        }
        fetched = self.http.post(self.endpoint.list_url, data=payload)
        soup = BeautifulSoup(fetched.text or "", "html.parser")
        candidates = []
        seen = set()
        for row in soup.select("table tr"):
            row_text = row.get_text(" ", strip=True)
            if not row_text or not TIME_RE.search(row_text):
                continue
            match = ACPT_RE.search(str(row))
            if not match:
                continue
            acptno = match.group(1)
            if acptno in seen:
                continue
            seen.add(acptno)
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            report_title = ""
            company = ""
            for anchor in row.find_all("a"):
                text = anchor.get_text(" ", strip=True)
                if len(text) >= 4 and not report_title:
                    report_title = text
            if len(cells) >= 3:
                company = cells[1].strip()
                if len(cells[2].strip()) >= 4:
                    report_title = cells[2].strip()
            if not report_title:
                continue
            time_match = TIME_RE.search(row_text)
            published_at = None
            if time_match:
                published_at = now.replace(
                    hour=int(time_match.group(1)),
                    minute=int(time_match.group(2)),
                    second=0,
                    microsecond=0,
                )
            viewer_url = (
                "https://kind.krx.co.kr/common/disclsviewer.do"
                f"?method=search&acptno={acptno}&docno=&viewerhost=&viewerport="
            )
            candidates.append(
                ArticleCandidate(
                    source_id=self.endpoint.source_id,
                    endpoint_id=self.endpoint.endpoint_id,
                    url=viewer_url,
                    external_id=acptno,
                    title_hint=report_title,
                    published_at_hint=published_at,
                    category_hint="DISCLOSURE",
                    metadata={"acptno": acptno, "company_name": company, "row_text": row_text},
                )
            )
        if not candidates:
            raise DiscoverError("KIND returned no disclosure rows or its table structure changed")
        return candidates

    def fetch(self, candidate):
        # DART handles the full disclosure document. KIND is an independent official
        # confirmation source, so we keep metadata without a second viewer request.
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
            published_date=candidate.published_at_hint.date().isoformat() if candidate.published_at_hint else now.date().isoformat(),
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
