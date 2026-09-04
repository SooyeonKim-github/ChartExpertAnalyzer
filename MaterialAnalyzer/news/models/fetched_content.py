from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FetchedContent:
    url: str
    status_code: int
    content_type: str
    text: Optional[str] = None
    raw_bytes: Optional[bytes] = None
    fetched_at: Optional[datetime] = None
    encoding: Optional[str] = None
