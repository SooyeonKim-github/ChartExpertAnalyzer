from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from ..exceptions import AccessDeniedError, FetchError, RateLimitError
from ..models import FetchedContent
from .rate_limiter import RateLimiter


class HttpClient:
    def __init__(self, timeout_sec: int = 10, max_retries: int = 3, min_interval_sec: float = 0.2, user_agent: str = "ChartExpertAnalyzer-NewsCollector/1.0"):
        self.timeout_sec = timeout_sec
        self.max_retries = max(1, max_retries)
        self.rate_limiter = RateLimiter(min_interval_sec)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def get(self, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> FetchedContent:
        return self._request("GET", url, params=params, headers=headers)

    def post(
        self,
        url: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> FetchedContent:
        return self._request("POST", url, params=params, data=data, json=json, headers=headers)

    def _request(self, method: str, url: str, **kwargs) -> FetchedContent:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self.rate_limiter.wait()
            try:
                response = self.session.request(method, url, timeout=self.timeout_sec, **kwargs)
                if response.status_code in (401, 403):
                    raise AccessDeniedError(f"access denied status={response.status_code} url={url}")
                if response.status_code == 429:
                    raise RateLimitError(f"rate limited url={url}")
                if 400 <= response.status_code < 500:
                    raise FetchError(f"client error status={response.status_code} url={url}")
                response.raise_for_status()
                return FetchedContent(
                    url=response.url,
                    status_code=response.status_code,
                    content_type=response.headers.get("Content-Type", ""),
                    text=response.text,
                    raw_bytes=response.content,
                    fetched_at=datetime.now(timezone.utc),
                    encoding=response.encoding,
                )
            except (AccessDeniedError, RateLimitError):
                raise
            except (requests.RequestException, FetchError) as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    time.sleep(2 ** attempt)
        raise FetchError(f"request failed method={method} url={url}: {last_error}")
