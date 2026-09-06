from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Tuple


def _json_tuple(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item))
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed if str(item))


def _row_value(row, key: str, default=""):
    if key not in row.keys():
        return default
    value = row[key]
    return default if value is None else value


@dataclass(frozen=True)
class LinkInput:
    event_id: str
    event_type: str
    event_stage: str
    event_title: str
    event_summary: str
    positive_negative: str
    material_score: float
    material_status: str
    companies: Tuple[str, ...] = field(default_factory=tuple)
    stock_codes: Tuple[str, ...] = field(default_factory=tuple)
    novelty_status: str = ""
    original_source_id: str = ""
    event_updated_at: str | None = None
    score_updated_at: str | None = None

    @classmethod
    def from_row(cls, row) -> "LinkInput":
        return cls(
            event_id=row["event_id"],
            event_type=_row_value(row, "event_type", "UNKNOWN") or "UNKNOWN",
            event_stage=_row_value(row, "event_stage", "UNKNOWN") or "UNKNOWN",
            event_title=_row_value(row, "event_title", ""),
            event_summary=_row_value(row, "event_summary", ""),
            positive_negative=_row_value(row, "positive_negative", "NEUTRAL") or "NEUTRAL",
            material_score=float(_row_value(row, "material_score", 0) or 0),
            material_status=_row_value(row, "material_status", "REJECT") or "REJECT",
            companies=_json_tuple(_row_value(row, "companies_json", None)),
            stock_codes=_json_tuple(_row_value(row, "stock_codes_json", None)),
            novelty_status=_row_value(row, "novelty_status", ""),
            original_source_id=_row_value(row, "original_source_id", ""),
            event_updated_at=_row_value(row, "event_updated_at", None),
            score_updated_at=_row_value(row, "score_updated_at", None),
        )


@dataclass(frozen=True)
class TickerRef:
    ticker: str
    name: str
    aliases: Tuple[str, ...] = field(default_factory=tuple)
    market: str = ""
    sector: str = ""
    industry: str = ""


@dataclass(frozen=True)
class ThemeRule:
    theme: str
    event_types: Tuple[str, ...]
    keywords: Tuple[str, ...]
    strong_keywords: Tuple[str, ...] = field(default_factory=tuple)
    weak_keywords: Tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.8
    min_materiality: float = 70.0


@dataclass(frozen=True)
class ThemeMatch:
    theme: str
    confidence: float
    matched_keywords: Tuple[str, ...]
    rule: ThemeRule | None = None


@dataclass(frozen=True)
class ThemeMaterialityResult:
    theme: str
    score: float
    eligible: bool
    strong_hits: Tuple[str, ...] = field(default_factory=tuple)
    weak_hits: Tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""


@dataclass(frozen=True)
class ThemeTickerRef:
    theme: str
    ticker: str
    name: str
    relation_type: str
    relation_weight: float
    confidence: float
    mapping_relevance: float
    reason: str


@dataclass(frozen=True)
class CompanyRelationship:
    subject_name: str
    subject_ticker: str
    related_ticker: str
    related_name: str
    relation_type: str
    relation_weight: float
    confidence: float
    evidence: str


@dataclass(frozen=True)
class TickerLinkRecord:
    event_id: str
    ticker: str
    name: str
    relation_type: str
    relation_weight: float
    mapping_relevance: float
    link_confidence: float
    theme: str
    theme_materiality_score: float
    link_reason: str
    evidence: str
    material_score: float
    material_status: str
    ticker_material_score: float
    positive_negative: str
    link_version: str
    reference_signature: str
    event_updated_at: str | None
    score_updated_at: str | None


@dataclass
class TickerLinkRunResult:
    processed: int = 0
    linked_events: int = 0
    unresolved_events: int = 0
    total_links: int = 0
    total_events: int = 0
    direct: int = 0
    supplier: int = 0
    customer: int = 0
    sector: int = 0
    theme: int = 0
