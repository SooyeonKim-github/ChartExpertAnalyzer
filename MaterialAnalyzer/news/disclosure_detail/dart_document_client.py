from __future__ import annotations

import os

from ..http import HttpClient


class DartDocumentError(RuntimeError):
    pass


class DartDocumentClient:
    URL = "https://opendart.fss.or.kr/api/document.xml"

    def __init__(self, api_key: str | None = None, http: HttpClient | None = None):
        self.api_key = (api_key or os.getenv("OPENDART_API_KEY", "")).strip()
        self.http = http or HttpClient(timeout_sec=20, max_retries=3, min_interval_sec=0.25)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def download(self, rcept_no: str) -> bytes:
        if not self.api_key:
            raise DartDocumentError("OPENDART_API_KEY is not set")
        rcept_no = str(rcept_no or "").strip()
        if not rcept_no:
            raise DartDocumentError("rcept_no is empty")

        fetched = self.http.get(
            self.URL,
            params={"crtfc_key": self.api_key, "rcept_no": rcept_no},
        )
        payload = fetched.raw_bytes or b""
        if payload[:2] == b"PK":
            return payload

        # OpenDART returns XML/JSON-like error bodies when the file cannot be served.
        text = (fetched.text or payload[:1000].decode("utf-8", errors="replace")).strip()
        compact = " ".join(text.split())[:500]
        raise DartDocumentError(f"OpenDART document response is not ZIP: {compact}")
