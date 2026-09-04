from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ArticleCandidate:
    source_id: str
    endpoint_id: str
    url: str
    external_id: Optional[str] = None
    title_hint: Optional[str] = None
    published_at_hint: Optional[datetime] = None
    summary_hint: Optional[str] = None
    category_hint: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
