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
    """KRX KIND today's-disclosure collector.

    KIND renders the public main screen and the disclosure rows separately. We first
    use the long-standing official POST sub-screen and then fall back to the public
    KOSPI/KOSDAQ main screens. A row can still be stored when an acceptance number
    is not exposed in the HTML; in that case a stable row hash is used because DART
    remains the canonical full-disclosure source.
    """

    MARKET_TYPES = ("1", "2")

    def discover(self):
        now = datetime.now(KST)
        candidates = []
        seen = set()

        # Primary: official POST sub-screen used by KIND's today-disclosure page.
        for today_flag in ("Y", "N"):
            payload = {
                "method": "searchTodayDisclosureSub",
                "currentPageSize": "100",
                "pageIndex": "1",
                "orderMode": "0",
                "orderStat": "D",
                "forward": "todaydisclosure_sub",
                "chose": "S",
                "todayFlag": today_flag,
                "selDate": now.strftime("%Y-%m-%d"),
            }
            fetched = self.http.post(self.endpoint.list_url, data=payload)
            self._append_rows(
                fetched.text or "",
                fetched.url,
                now,
                candidates,
                seen,
                market_type="ALL",
                response_mode=f"POST_{today_flag}",
            )
            if candidates:
                break

        # Fallback: public market screens. Some deployments only expose the shell,
        # but this path is useful when rows are server-rendered.
        if not candidates:
            for market_type in self.MARKET_TYPES:
                params = {
                    "method": "searchTodayDisclosureMain",
                    "marketType": market_type,
                }
                fetched = self.http.get(self.endpoint.list_url, params=params)
                self._append_rows(
                    fetched.text or "",
                    fetched.url,
                    now,
                    candidates,
                    seen,
                    market_type=market_type,
                    response_mode="GET_MAIN",
                )

        if not candidates:
            raise DiscoverError(
                "KIND returned no disclosure rows from POST sub-screen or public main screens"
            )
        return candidates

    def _append_rows(
        self,
        html: str,
        page_url: str,
        now: datetime,
        candidates: list[ArticleCandidate],
        seen: set[str],
        *,
        market_type: str,
        response_mode: str,
    ) -> None:
        soup = BeautifulSoup(html, "html.parser")

        for row in soup.select("tr"):
            row_text = row.get_text(" ", strip=True)
            if not row_text:
                continue

            cells = [
                cell.get_text(" ", strip=True)
                for cell in row.find_all(["td", "th"])
                if cell.get_text(" ", strip=True)
            ]
            if len(cells) < 2:
                continue

            time_match = TIME_RE.search(row_text)
            row_html = str(row)
            acpt_match = ACPT_RE.search(row_html)
            acptno = acpt_match.group(1) if acpt_match else ""

            # Ignore headers/navigation. A real disclosure row normally has a time
            # or an acceptance number in onclick/href markup.
            if not time_match and not acptno:
                continue

            company, report_title = self._guess_company_title(row, cells)
            if len(report_title) < 4:
                continue

            published_at = None
            if time_match:
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
                    f"{now:%Y%m%d}|{market_type}|{time_match.group(0) if time_match else ''}|"
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
                        "response_mode": response_mode,
                    },
                )
            )

    @staticmethod
    def _guess_company_title(row, cells: list[str]) -> tuple[str, str]:
        company = ""
        report_title = ""

        # The traditional KIND table is: time / company / disclosure title / submitter / chart.
        if len(cells) >= 3 and TIME_RE.search(cells[0]):
            company = cells[1].strip()
            report_title = cells[2].strip()

        # Fall back to meaningful anchor text when cell positions differ.
        anchor_texts = []
        for anchor in row.find_all("a"):
            text = anchor.get_text(" ", strip=True)
            if len(text) >= 2 and text not in anchor_texts:
                anchor_texts.append(text)
        if not report_title and anchor_texts:
            report_title = max(anchor_texts, key=len)
        if not company and len(anchor_texts) >= 2:
            shorter = [text for text in anchor_texts if text != report_title]
            if shorter:
                company = shorter[0]

        # Last resort: remove the time cell and use the next two visible cells.
        if not report_title:
            visible = [text for text in cells if not TIME_RE.fullmatch(text)]
            if len(visible) >= 2:
                company = company or visible[0]
                report_title = visible[1]

        return company, report_title

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
