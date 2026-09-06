from __future__ import annotations

import json
from datetime import datetime, timezone

from MaterialAnalyzer.news.collectors.dart import DartCollector
from MaterialAnalyzer.news.exceptions import DiscoverError
from MaterialAnalyzer.news.models import ArticleCandidate


class DartRangeCollector(DartCollector):
    """OpenDART date-range collector with deterministic ascending pagination."""

    def __init__(self, endpoint, start_date, end_date, http_client=None):
        super().__init__(endpoint, http_client=http_client)
        self.start_date = start_date
        self.end_date = end_date

    def discover(self):
        candidates: list[ArticleCandidate] = []
        page_no = 1
        page_count = 100
        while True:
            params = {
                "crtfc_key": self._api_key(),
                "bgn_de": self.start_date.strftime("%Y%m%d"),
                "end_de": self.end_date.strftime("%Y%m%d"),
                "page_no": str(page_no),
                "page_count": str(page_count),
                "sort": "date",
                "sort_mth": "asc",
            }
            fetched = self.http.get(self.endpoint.api_url or self.LIST_API, params=params)
            payload = json.loads(fetched.text or "{}")
            status = payload.get("status")
            if status not in (None, "000"):
                if status == "013":
                    return candidates
                raise DiscoverError(f"DART status={status} message={payload.get('message', '')}")

            items = payload.get("list", []) or []
            for item in items:
                rcept_no = item.get("rcept_no", "")
                if not rcept_no:
                    continue
                metadata = {
                    "corp_code": item.get("corp_code", ""),
                    "corp_name": item.get("corp_name", ""),
                    "stock_code": (item.get("stock_code") or "").strip(),
                    "report_nm": item.get("report_nm", ""),
                    "flr_nm": item.get("flr_nm", ""),
                    "rcept_dt": item.get("rcept_dt", ""),
                    "historical_range": True,
                }
                candidates.append(
                    ArticleCandidate(
                        source_id=self.endpoint.source_id,
                        endpoint_id=self.endpoint.endpoint_id,
                        url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                        external_id=rcept_no,
                        title_hint=item.get("report_nm", ""),
                        published_at_hint=self._parse_date(item.get("rcept_dt")),
                        category_hint="DISCLOSURE",
                        metadata=metadata,
                    )
                )

            total_page = int(payload.get("total_page") or 0)
            if (total_page and page_no >= total_page) or len(items) < page_count:
                break
            page_no += 1
        return candidates
