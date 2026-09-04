from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class RawArticle:
    article_id: str
    source_id: str
    endpoint_id: str
    source_name: str
    source_type: str
    source_grade: str
    title: str
    body: Optional[str]
    summary: Optional[str]
    url: str
    canonical_url: Optional[str]
    author: Optional[str]
    published_at: Optional[datetime]
    updated_at: Optional[datetime]
    collected_at: datetime
    published_date: Optional[str]
    market_date: Optional[str]
    category: Optional[str]
    language: str
    article_class: str
    collector_type: str
    content_mode: str
    external_id: Optional[str] = None
    published_at_precision: str = "UNKNOWN"
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    url_hash: Optional[str] = None
    title_hash: Optional[str] = None
    content_hash: Optional[str] = None
    duplicate_of: Optional[str] = None
    body_length: int = 0
    has_full_body: bool = False
    fetch_status: str = "SUCCESS"
    http_status: Optional[int] = None
    parse_status: str = "SUCCESS"
    error_code: Optional[str] = None
    material_candidate: bool = False
    analysis_status: str = "PENDING"
    processed_at: Optional[datetime] = None
    source_metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
