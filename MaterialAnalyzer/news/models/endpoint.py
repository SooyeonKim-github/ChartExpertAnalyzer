from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class SourceEndpoint:
    endpoint_id: str
    source_id: str
    source_name: str
    source_type: str
    source_grade: str
    priority: int
    collector_type: str
    endpoint_role: str
    target_section: str
    interval_min: int
    content_mode: str
    enabled: bool
    list_url: str = ""
    detail_url_template: str = ""
    fallback_source_id: str = ""
    category: str = ""
    item_selector: str = ""
    title_selector: str = ""
    link_selector: str = ""
    date_selector: str = ""
    body_selector: str = ""
    author_selector: str = ""
    api_url: str = ""
    rss_url: str = ""
    headers_json: str = ""
    extra: Dict[str, str] = field(default_factory=dict)

    def preferred_url(self) -> str:
        return self.api_url or self.rss_url or self.list_url
