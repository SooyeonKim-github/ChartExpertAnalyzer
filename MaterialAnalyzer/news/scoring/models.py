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


def _row_value(row, key: str, default=""):
    if key not in row.keys():
        return default
    value = row[key]
    return default if value is None else value


@dataclass(frozen=True)
class ScoreInput:
    event_id: str
    event_type: str
    event_stage: str
    event_title: str
    positive_negative: str
    companies: Tuple[str, ...] = field(default_factory=tuple)
    stock_codes: Tuple[str, ...] = field(default_factory=tuple)
    numbers: Tuple[str, ...] = field(default_factory=tuple)
    original_source_id: str = ""
    source_grade: str = ""
    source_type: str = ""
    source_count: int = 0
    confirmation_count: int = 0
    novelty_status: str = "NEW_EVENT"
    novelty_score: float = 0.0
    event_updated_at: str | None = None
    novelty_updated_at: str | None = None

    @classmethod
    def from_row(cls, row) -> "ScoreInput":
        return cls(
            event_id=row["event_id"],
            event_type=_row_value(row, "event_type", "UNKNOWN") or "UNKNOWN",
            event_stage=_row_value(row, "event_stage", "UNKNOWN") or "UNKNOWN",
            event_title=_row_value(row, "event_title", ""),
            positive_negative=_row_value(row, "positive_negative", "NEUTRAL") or "NEUTRAL",
            companies=_json_tuple(_row_value(row, "companies_json", None)),
            stock_codes=_json_tuple(_row_value(row, "stock_codes_json", None)),
            numbers=_json_tuple(_row_value(row, "numbers_json", None)),
            original_source_id=_row_value(row, "original_source_id", ""),
            source_grade=_row_value(row, "source_grade", ""),
            source_type=_row_value(row, "source_type", ""),
            source_count=int(_row_value(row, "source_count", 0) or 0),
            confirmation_count=int(_row_value(row, "confirmation_count", 0) or 0),
            novelty_status=_row_value(row, "novelty_status", "NEW_EVENT") or "NEW_EVENT",
            novelty_score=float(_row_value(row, "novelty_score", 0) or 0),
            event_updated_at=_row_value(row, "event_updated_at", None),
            novelty_updated_at=_row_value(row, "novelty_updated_at", None),
        )


@dataclass(frozen=True)
class MaterialScoreRecord:
    event_id: str
    material_score: float
    material_status: str
    direct_company_score: float
    event_certainty_score: float
    financial_impact_score: float
    quantification_score: float
    novelty_component_score: float
    source_reliability_score: float
    multi_source_score: float
    scoring_reason: str
    scoring_version: str
    event_updated_at: str | None
    novelty_updated_at: str | None


@dataclass
class MaterialScoreRunResult:
    processed: int = 0
    inserted: int = 0
    updated: int = 0
    total_scores: int = 0
    strong: int = 0
    confirmed: int = 0
    watch: int = 0
    reject: int = 0
