from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple

@dataclass(frozen=True)
class ArticleFeatures:
    article_id: str
    source_id: str
    source_type: str
    source_grade: str
    article_class: str
    market_date: str | None
    normalized_title: str
    tokens: Tuple[str, ...] = field(default_factory=tuple)
    companies: Tuple[str, ...] = field(default_factory=tuple)
    stock_codes: Tuple[str, ...] = field(default_factory=tuple)
    numbers: Tuple[str, ...] = field(default_factory=tuple)
    event_type: str = "UNKNOWN"
    external_id: str | None = None

@dataclass(frozen=True)
class MatchResult:
    score: float
    method: str
    reason: str
