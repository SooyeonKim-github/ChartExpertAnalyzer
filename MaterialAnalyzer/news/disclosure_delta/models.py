from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class DisclosureDeltaInput:
    event_id: str
    canonical_event_key: str
    event_type: str
    event_stage: str
    event_title: str
    event_summary: str
    positive_negative: str
    companies: Tuple[str, ...] = field(default_factory=tuple)
    stock_codes: Tuple[str, ...] = field(default_factory=tuple)
    numbers: Tuple[str, ...] = field(default_factory=tuple)
    original_source_id: str = ""
    first_seen_at: str | None = None
    market_date: str | None = None
    event_updated_at: str | None = None


@dataclass(frozen=True)
class DisclosureDeltaRecord:
    event_id: str
    parent_event_id: str | None
    is_revision: bool
    parent_match_method: str
    parent_match_confidence: float
    delta_type: str
    delta_direction: str
    previous_numbers: Tuple[str, ...]
    current_numbers: Tuple[str, ...]
    numeric_kind: str
    previous_numeric_value: float | None
    current_numeric_value: float | None
    numeric_change: float | None
    numeric_change_pct: float | None
    effective_sentiment: str
    score_adjustment: float
    delta_reason: str
    analysis_version: str
    event_updated_at: str | None


@dataclass
class DisclosureDeltaRunResult:
    processed: int = 0
    inserted: int = 0
    updated: int = 0
    total: int = 0
    originals: int = 0
    revisions: int = 0
    unresolved: int = 0
    increases: int = 0
    decreases: int = 0
    minor: int = 0
