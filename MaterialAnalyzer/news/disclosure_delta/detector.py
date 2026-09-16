from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from ..clustering.feature_extractor import normalize_title
from ..events.event_identity import GENERIC_DISCLOSURE_ANCHORS
from .models import DisclosureDeltaInput, DisclosureDeltaRecord


REVISION_RE = re.compile(
    r"^\s*(?:\[(?:기재정정|본문정정|첨부정정|정정)\]|\((?:기재정정|본문정정|첨부정정|정정)\)|"
    r"(?:기재정정|본문정정|첨부정정|정정)\s*)",
    re.I,
)
SCHEDULE_RE = re.compile(r"계약기간|계약 기간|종료일|기간연장|기간 연장|납기|일정변경|일정 변경", re.I)
NUMBER_RE = re.compile(r"^\s*([-+]?\d[\d,]*(?:\.\d+)?)\s*(조원|억원|만원|원|%|퍼센트|GW|MW|kW|GWh|MWh|kWh|개|건|대|척|명|회)?\s*$", re.I)


@dataclass(frozen=True)
class ParsedNumber:
    raw: str
    kind: str
    value: float


def is_revision_title(title: str | None) -> bool:
    return bool(REVISION_RE.search(title or ""))


def revision_base_title(title: str | None) -> str:
    raw = REVISION_RE.sub("", title or "").strip()
    return normalize_title(raw)


def _json_tuple(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(x) for x in value if str(x))
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ()
    return tuple(str(x) for x in parsed if str(x)) if isinstance(parsed, list) else ()


def input_from_row(row) -> DisclosureDeltaInput:
    def get(key, default=""):
        return row[key] if key in row.keys() and row[key] is not None else default

    return DisclosureDeltaInput(
        event_id=get("event_id"),
        canonical_event_key=get("canonical_event_key"),
        event_type=get("event_type", "UNKNOWN") or "UNKNOWN",
        event_stage=get("event_stage", "UNKNOWN") or "UNKNOWN",
        event_title=get("event_title"),
        event_summary=get("event_summary"),
        positive_negative=get("positive_negative", "NEUTRAL") or "NEUTRAL",
        companies=_json_tuple(get("companies_json", None)),
        stock_codes=_json_tuple(get("stock_codes_json", None)),
        numbers=_json_tuple(get("numbers_json", None)),
        original_source_id=get("original_source_id"),
        first_seen_at=get("first_seen_at", None),
        market_date=get("market_date", None),
        event_updated_at=get("updated_at", None),
    )


def parse_number(raw: str) -> ParsedNumber | None:
    match = NUMBER_RE.match(str(raw or "").strip())
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (match.group(2) or "").casefold()
    if unit == "조원":
        return ParsedNumber(raw, "money", value * 1_000_000_000_000)
    if unit == "억원":
        return ParsedNumber(raw, "money", value * 100_000_000)
    if unit == "만원":
        return ParsedNumber(raw, "money", value * 10_000)
    if unit == "원":
        return ParsedNumber(raw, "money", value)
    if unit in {"%", "퍼센트"}:
        return ParsedNumber(raw, "percent", value)
    if unit in {"gw", "mw", "kw"}:
        scale = {"gw": 1_000_000, "mw": 1_000, "kw": 1}[unit]
        return ParsedNumber(raw, "power_kw", value * scale)
    if unit in {"gwh", "mwh", "kwh"}:
        scale = {"gwh": 1_000_000, "mwh": 1_000, "kwh": 1}[unit]
        return ParsedNumber(raw, "energy_kwh", value * scale)
    if unit in {"개", "건", "대", "척", "명", "회"}:
        return ParsedNumber(raw, "quantity", value)
    return ParsedNumber(raw, "plain", value)


def comparable_pair(previous: tuple[str, ...], current: tuple[str, ...]) -> tuple[ParsedNumber, ParsedNumber] | None:
    previous_parsed = [x for x in (parse_number(v) for v in previous) if x]
    current_parsed = [x for x in (parse_number(v) for v in current) if x]
    priority = ("money", "percent", "power_kw", "energy_kwh", "quantity", "plain")
    for kind in priority:
        left = [x for x in previous_parsed if x.kind == kind]
        right = [x for x in current_parsed if x.kind == kind]
        if len(left) == 1 and len(right) == 1:
            return left[0], right[0]
    return None


def _directional_sentiment(event_type: str, direction: str) -> str:
    event_type = (event_type or "").upper()
    if event_type in {"ORDER_CONTRACT", "BUYBACK", "DIVIDEND"}:
        if direction == "INCREASE":
            return "POSITIVE"
        if direction == "DECREASE":
            return "NEGATIVE"
    if event_type in {"SANCTION", "DERIVATIVE_LOSS", "RECALL"}:
        if direction == "INCREASE":
            return "NEGATIVE"
        if direction == "DECREASE":
            return "POSITIVE"
    return "NEUTRAL"


def _typed_delta(event_type: str, direction: str) -> str:
    prefix = {
        "ORDER_CONTRACT": "CONTRACT",
        "BUYBACK": "BUYBACK",
        "DIVIDEND": "DIVIDEND",
        "CAPEX": "CAPEX",
        "CAPITAL_RAISE": "CAPITAL_RAISE",
    }.get((event_type or "").upper(), "VALUE")
    return f"{prefix}_{direction}"


class DisclosureDeltaDetector:
    VERSION = "RULE_DISCLOSURE_DELTA_V1"

    def detect(self, current: DisclosureDeltaInput, parent: DisclosureDeltaInput | None,
               *, parent_match_method: str = "", parent_match_confidence: float = 0.0,
               ambiguous_parent: bool = False) -> DisclosureDeltaRecord:
        revision = is_revision_title(current.event_title)
        if not revision:
            return DisclosureDeltaRecord(
                event_id=current.event_id,
                parent_event_id=None,
                is_revision=False,
                parent_match_method="",
                parent_match_confidence=0.0,
                delta_type="ORIGINAL",
                delta_direction="NONE",
                previous_numbers=(),
                current_numbers=current.numbers,
                numeric_kind="",
                previous_numeric_value=None,
                current_numeric_value=None,
                numeric_change=None,
                numeric_change_pct=None,
                effective_sentiment=current.positive_negative or "NEUTRAL",
                score_adjustment=0.0,
                delta_reason="original disclosure; no revision prefix",
                analysis_version=self.VERSION,
                event_updated_at=current.event_updated_at,
            )

        if parent is None:
            reason = "revision detected but parent disclosure is ambiguous" if ambiguous_parent else "revision detected but no reliable parent disclosure found"
            return DisclosureDeltaRecord(
                event_id=current.event_id,
                parent_event_id=None,
                is_revision=True,
                parent_match_method=parent_match_method,
                parent_match_confidence=parent_match_confidence,
                delta_type="REVISION_UNRESOLVED",
                delta_direction="UNKNOWN",
                previous_numbers=(),
                current_numbers=current.numbers,
                numeric_kind="",
                previous_numeric_value=None,
                current_numeric_value=None,
                numeric_change=None,
                numeric_change_pct=None,
                effective_sentiment="NEUTRAL",
                score_adjustment=-25.0,
                delta_reason=reason,
                analysis_version=self.VERSION,
                event_updated_at=current.event_updated_at,
            )

        text = f"{current.event_title} {current.event_summary}"
        if SCHEDULE_RE.search(text):
            return DisclosureDeltaRecord(
                event_id=current.event_id,
                parent_event_id=parent.event_id,
                is_revision=True,
                parent_match_method=parent_match_method,
                parent_match_confidence=parent_match_confidence,
                delta_type="SCHEDULE_CHANGE",
                delta_direction="NEUTRAL",
                previous_numbers=parent.numbers,
                current_numbers=current.numbers,
                numeric_kind="",
                previous_numeric_value=None,
                current_numeric_value=None,
                numeric_change=None,
                numeric_change_pct=None,
                effective_sentiment="NEUTRAL",
                score_adjustment=-15.0,
                delta_reason="revision is primarily a schedule/period change",
                analysis_version=self.VERSION,
                event_updated_at=current.event_updated_at,
            )

        pair = comparable_pair(parent.numbers, current.numbers)
        if pair:
            previous_value, current_value = pair
            change = current_value.value - previous_value.value
            pct = None
            if not math.isclose(previous_value.value, 0.0):
                pct = change / abs(previous_value.value) * 100.0
            tolerance = max(abs(previous_value.value) * 0.01, 1e-12)
            if change > tolerance:
                direction = "INCREASE"
            elif change < -tolerance:
                direction = "DECREASE"
            else:
                direction = "UNCHANGED"

            if direction in {"INCREASE", "DECREASE"}:
                delta_type = _typed_delta(current.event_type, direction)
                sentiment = _directional_sentiment(current.event_type, direction)
                # material_score means market importance, not bullishness. A large negative
                # correction can be just as material as a positive one; direction belongs
                # in effective_sentiment, while a verified numeric delta gets a small
                # materiality bonus in either direction.
                adjustment = 5.0
                reason = f"comparable {previous_value.kind} changed from {previous_value.raw} to {current_value.raw}"
            else:
                delta_type = "MINOR_REVISION"
                sentiment = "NEUTRAL"
                adjustment = -20.0
                reason = f"comparable {previous_value.kind} is effectively unchanged"

            return DisclosureDeltaRecord(
                event_id=current.event_id,
                parent_event_id=parent.event_id,
                is_revision=True,
                parent_match_method=parent_match_method,
                parent_match_confidence=parent_match_confidence,
                delta_type=delta_type,
                delta_direction=direction,
                previous_numbers=parent.numbers,
                current_numbers=current.numbers,
                numeric_kind=previous_value.kind,
                previous_numeric_value=previous_value.value,
                current_numeric_value=current_value.value,
                numeric_change=change,
                numeric_change_pct=round(pct, 4) if pct is not None else None,
                effective_sentiment=sentiment,
                score_adjustment=adjustment,
                delta_reason=reason,
                analysis_version=self.VERSION,
                event_updated_at=current.event_updated_at,
            )

        if parent.numbers != current.numbers and (parent.numbers or current.numbers):
            delta_type = "NUMERIC_REVISION"
            reason = "meaningful numbers changed but no single like-for-like numeric pair was reliable"
            adjustment = -10.0
        else:
            delta_type = "MINOR_REVISION"
            reason = "revision has no reliable material numeric delta"
            adjustment = -20.0

        return DisclosureDeltaRecord(
            event_id=current.event_id,
            parent_event_id=parent.event_id,
            is_revision=True,
            parent_match_method=parent_match_method,
            parent_match_confidence=parent_match_confidence,
            delta_type=delta_type,
            delta_direction="UNKNOWN" if delta_type == "NUMERIC_REVISION" else "NEUTRAL",
            previous_numbers=parent.numbers,
            current_numbers=current.numbers,
            numeric_kind="",
            previous_numeric_value=None,
            current_numeric_value=None,
            numeric_change=None,
            numeric_change_pct=None,
            effective_sentiment="NEUTRAL",
            score_adjustment=adjustment,
            delta_reason=reason,
            analysis_version=self.VERSION,
            event_updated_at=current.event_updated_at,
        )


def generic_revision_anchor(title: str | None) -> bool:
    return revision_base_title(title) in GENERIC_DISCLOSURE_ANCHORS
