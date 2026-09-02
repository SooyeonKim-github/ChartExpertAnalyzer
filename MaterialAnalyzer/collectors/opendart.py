from __future__ import annotations

from datetime import date, timedelta

import requests

from ..config import MaterialCollectorConfig
from ..models import CollectedItem


class OpenDartCollector:
    source_name = "opendart"

    def __init__(self, config: MaterialCollectorConfig) -> None:
        self.config = config

    def available(self) -> bool:
        return bool(self.config.opendart_api_key())

    def collect(self, end_date: date, days: int, collected_at: str) -> list[CollectedItem]:
        api_key = self.config.opendart_api_key()
        if not api_key:
            return []

        begin_date = end_date - timedelta(days=max(days - 1, 0))
        out: list[CollectedItem] = []

        for page_no in range(1, self.config.opendart_max_pages + 1):
            params = {
                "crtfc_key": api_key,
                "bgn_de": begin_date.strftime("%Y%m%d"),
                "end_de": end_date.strftime("%Y%m%d"),
                "page_no": page_no,
                "page_count": self.config.opendart_page_count,
            }
            response = requests.get(
                self.config.opendart_api_url,
                params=params,
                headers={"User-Agent": self.config.user_agent},
                timeout=self.config.request_timeout_sec,
            )
            response.raise_for_status()
            payload = response.json()
            status = str(payload.get("status", ""))
            if status == "013":  # no data
                break
            if status and status != "000":
                raise RuntimeError(f"OpenDART error {status}: {payload.get('message', '')}")

            rows = payload.get("list") or []
            if not rows:
                break

            for raw in rows:
                receipt_no = str(raw.get("rcept_no") or "")
                report_name = str(raw.get("report_nm") or "")
                corp_name = str(raw.get("corp_name") or "")
                title = f"{corp_name} | {report_name}" if corp_name else report_name
                url = (
                    f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}"
                    if receipt_no
                    else ""
                )
                haystack = title
                out.append(
                    CollectedItem(
                        collected_at=collected_at,
                        published_at=str(raw.get("rcept_dt") or ""),
                        source_type="disclosure",
                        source=self.source_name,
                        title=title,
                        summary=str(raw.get("flr_nm") or ""),
                        url=url,
                        category=str(raw.get("pblntf_ty") or ""),
                        ticker=str(raw.get("stock_code") or "").strip(),
                        corp_code=str(raw.get("corp_code") or "").strip(),
                        report_code=receipt_no,
                        future_hint=any(k in haystack for k in self.config.future_hint_keywords),
                    )
                )

            total_page = int(payload.get("total_page") or page_no)
            if page_no >= total_page:
                break

        return out
