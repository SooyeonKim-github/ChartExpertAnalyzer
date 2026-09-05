from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Tuple


def _json_tuple(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(str(item) for item in value if str(item))
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed if str(item))


@dataclass(frozen=True)
class EventView:
    event_id: str
    cluster_id: str
    event_type: str
    event_stage: str
    event_title: str
    event_summary: str
    positive_negative: str
    companies: Tuple[str, ...] = field(default_factory=tuple)
    stock_codes: Tuple[str, ...] = field(default_factory=tuple)
    numbers: Tuple[str, ...] = field(default_factory=tuple)
    original_source_id: str = ""
    source_grade: str = ""
    source_type: str = ""
    article_class: str = ""
    source_count: int = 0
    confirmation_count: int = 0
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    market_date: str | None = None
    updated_at: str | None = None
    material_candidate: bool = True

    @classmethod
    def from_row(cls, row) -> "EventView":
        return cls(
            event_id=row["event_id"],
            cluster_id=row["cluster_id"],
            event_type=row["event_type"] or "UNKNOWN",
            event_stage=row["event_stage"] or "UNKNOWN",
            event_title=row["event_title"] or "",
            event_summary=row["event_summary"] or "",
            positive_negative=row["positive_negative"] or "NEUTRAL",
            companies=_json_tuple(row["companies_json"]),
            stock_codes=_json_tuple(row["stock_codes_json"]),
            numbers=_json_tuple(row["numbers_json"]),
            original_source_id=row["original_source_id"] or "",
            source_grade=row["source_grade"] or "" if "source_grade" in row.keys() else "",
            source_type=row["source_type"] or "" if "source_type" in row.keys() else "",
            article_class=row["article_class"] or "" if "article_class" in row.keys() else "",
            source_count=int(row["source_count"] or 0),
            confirmation_count=int(row["confirmation_count"] or 0),
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            market_date=row["market_date"],
            updated_at=row["updated_at"],
            material_candidate=bool(int(row["material_candidate"] or 0)),
        )


@dataclass(frozen=True)
class RelationResult:
    score: float
    title_ratio: float
    token_overlap: float
    days_apart: int | None
    reason: str


@dataclass(frozen=True)
class DeltaResult:
    stage_changed: bool = False
    stage_progressed: bool = False
    number_changed: bool = False
    company_changed: bool = False
    polarity_changed: bool = False
    source_reliability_increased: bool = False
    confirmation_source_added: bool = False
    new_information_count: int = 0
    previous_stage: str = ""
    current_stage: str = ""
    previous_numbers: Tuple[str, ...] = field(default_factory=tuple)
    current_numbers: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NoveltyDecision:
    novelty_status: str
    novelty_score: float
    reason: str


@dataclass(frozen=True)
class NoveltyRecord:
    event_id: str
    family_id: str
    parent_event_id: str | None
    novelty_status: str
    novelty_score: float
    relation_score: float
    days_since_parent: int | None
    stage_changed: bool
    stage_progressed: bool
    number_changed: bool
    company_changed: bool
    polarity_changed: bool
    source_reliability_increased: bool
    confirmation_source_added: bool
    new_information_count: int
    previous_stage: str
    current_stage: str
    previous_numbers: Tuple[str, ...]
    current_numbers: Tuple[str, ...]
    novelty_reason: str
    analysis_version: str
    event_updated_at: str | None


@dataclass
class NoveltyRunResult:
    processed: int = 0
    inserted: int = 0
    updated: int = 0
    total_novelty: int = 0
    total_families: int = 0
    new_event: int = 0
    follow_up: int = 0
    confirmation: int = 0
    rehash: int = 0
    market_reaction: int = 0
