from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class MaterialEvent:
    event_id: str
    cluster_id: str
    representative_article_id: str
    event_type: str
    event_stage: str
    event_title: str
    event_summary: str
    positive_negative: str
    quantified: bool
    material_candidate: bool = False
    material_candidate_reason: str = ""
    classification_source: str = "NONE"
    companies: Tuple[str, ...] = field(default_factory=tuple)
    stock_codes: Tuple[str, ...] = field(default_factory=tuple)
    numbers: Tuple[str, ...] = field(default_factory=tuple)
    original_source_id: str = ""
    original_source_name: str = ""
    article_count: int = 0
    source_count: int = 0
    confirmation_count: int = 0
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    market_date: str | None = None
    extraction_confidence: float = 0.0
    extraction_version: str = "RULE_EVENT_V1_1"
    cluster_updated_at: str | None = None


@dataclass
class EventRunResult:
    processed: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    total_events: int = 0
