from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from ..exceptions import ConfigurationError, DiscoverError
from ..models import ArticleCandidate, FetchedContent, RawArticle
from .base import BaseCollector
from .factory import CollectorFactory


@CollectorFactory.register("DART_API")
class DartCollector(BaseCollector):
    LIST_API = "https://opendart.fss.or.kr/api/list.json"

    def _api_key(self) -> str:
        key = os.getenv("OPENDART_API_KEY", "").strip()
        if not key:
            raise ConfigurationError("OPENDART_API_KEY is not set")
        return key

    def discover(self):
        end = datetime.now(timezone.utc).date()
        begin = end - timedelta(days=2)
        params = {"crtfc_key": self._api_key(), "bgn_de": begin.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"), "page_count": "100", "sort": "date", "sort_mth": "desc"}
        fetched = self.http.get(self.endpoint.api_url or self.LIST_API, params=params)
        payload = json.loads(fetched.text or "{}")
        status = payload.get("status")
        if status not in (None, "000"):
            if status == "013":
                return []
            raise DiscoverError(f"DART status={status} message={payload.get('message', '')}")
        candidates = []
        for item in payload.get("list", []):
            rcept_no = item.get("rcept_no", "")
            if not rcept_no:
                continue
            metadata = {"corp_code": item.get("corp_code", ""), "corp_name": item.get("corp_name", ""), "stock_code": (item.get("stock_code") or "").strip(), "report_nm": item.get("report_nm", ""), "flr_nm": item.get("flr_nm", ""), "rcept_dt": item.get("rcept_dt", "")}
            candidates.append(ArticleCandidate(source_id=self.endpoint.source_id, endpoint_id=self.endpoint.endpoint_id, url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}", external_id=rcept_no, title_hint=item.get("report_nm", ""), published_at_hint=self._parse_date(item.get("rcept_dt")), category_hint="DISCLOSURE", metadata=metadata))
        return candidates

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def fetch(self, candidate):
        return FetchedContent(url=candidate.url, status_code=200, content_type="application/vnd.opendart.metadata+json", text=json.dumps(candidate.metadata, ensure_ascii=False), fetched_at=datetime.now(timezone.utc))

    def parse(self, candidate, fetched):
        now = datetime.now(timezone.utc)
        rcept_no = candidate.external_id or hashlib.sha256(candidate.url.encode("utf-8")).hexdigest()[:12]
        title = candidate.title_hint or candidate.metadata.get("report_nm", "")
        return RawArticle(article_id=f"DART_{rcept_no}", source_id=self.endpoint.source_id, endpoint_id=self.endpoint.endpoint_id, source_name=self.endpoint.source_name, source_type=self.endpoint.source_type, source_grade=self.endpoint.source_grade, title=title, body=None, summary=None, url=candidate.url, canonical_url=candidate.url, author=candidate.metadata.get("flr_nm") or None, published_at=candidate.published_at_hint, updated_at=None, collected_at=now, published_date=candidate.published_at_hint.date().isoformat() if candidate.published_at_hint else None, market_date=None, category="DISCLOSURE", language="ko", article_class="DISCLOSURE", collector_type=self.endpoint.collector_type, content_mode=self.endpoint.content_mode, body_length=0, has_full_body=False, http_status=fetched.status_code, source_metadata=candidate.metadata)
