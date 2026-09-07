from __future__ import annotations

import re

from .models import ScoreInput


OFFICIAL_GOV_SOURCES = {"MOTIR", "MSIT", "MCEE", "MFDS", "FSC"}
DISCLOSURE_SOURCES = {"DART", "KIND"}

POLICY_OR_SECTOR_EVENT_TYPES = {
    "GOV_POLICY", "SUBSIDY", "REGULATION", "AI", "AI_DATACENTER", "SEMICONDUCTOR",
    "SECONDARY_BATTERY", "DEFENSE", "NUCLEAR", "SHIPBUILDING", "BIO", "SUPPLY", "SHORTAGE",
}

# 20 points: how certain/realized the event is.
CERTAINTY_SCORE = {
    "COMPLETED": 20.0,
    "STARTED": 20.0,
    "APPROVED": 20.0,
    "RELEASED": 18.0,
    "CONFIRMED": 18.0,
    "ANNOUNCED": 12.0,
    "PLANNED": 10.0,
    "REQUESTED": 6.0,
    "UNKNOWN": 4.0,
}

# 30 points: intrinsic catalyst importance. This is deliberately the largest component.
# It measures whether the market should pay attention, not whether the stock should go up.
EVENT_IMPORTANCE_SCORE = {
    "ORDER_CONTRACT": 30.0,
    "MNA": 30.0,
    "EARNINGS": 30.0,
    "GUIDANCE": 30.0,
    "PUBLIC_OFFER": 29.0,
    "RESTRUCTURING": 29.0,
    "CAPEX": 28.0,
    "INVESTMENT": 28.0,
    "ASSET_TRANSACTION": 28.0,
    "CAPITAL_RAISE": 27.0,
    "BUYBACK": 27.0,
    "VALUE_UP": 27.0,
    "CAPITAL_REDUCTION": 27.0,
    "APPROVAL": 27.0,
    "CLINICAL": 26.0,
    "TRADING_HALT": 26.0,
    "SANCTION": 26.0,
    "RECALL": 25.0,
    "DIVIDEND": 24.0,
    "TREASURY_STOCK_DISPOSAL": 24.0,
    "CONVERTIBLE_EXERCISE": 24.0,
    "INVESTMENT_DISPOSAL": 24.0,
    "DERIVATIVE_LOSS": 24.0,
    "PRICE_INCREASE": 24.0,
    "SHORTAGE": 24.0,
    "GOV_POLICY": 24.0,
    "LITIGATION": 23.0,
    "SUBSIDY": 23.0,
    "DEFENSE": 23.0,
    "NUCLEAR": 23.0,
    "AI_DATACENTER": 23.0,
    "PRODUCT": 22.0,
    "CONVERTIBLE_ADJUSTMENT": 21.0,
    "FINANCING": 21.0,
    "MATERIAL_MANAGEMENT": 21.0,
    "AI": 21.0,
    "SEMICONDUCTOR": 21.0,
    "SECONDARY_BATTERY": 21.0,
    "SHIPBUILDING": 21.0,
    "BIO": 21.0,
    "DEBT_GUARANTEE": 21.0,
    "SHARE_CONSOLIDATION": 20.0,
    "PARTNERSHIP": 19.0,
    "SUPPLY": 19.0,
    "REGULATION": 19.0,
    "PATENT": 17.0,
    "OWNERSHIP_CHANGE": 17.0,
    "CORPORATE_GOVERNANCE": 10.0,
    "MARKET_QUERY": 8.0,
    "IR_EVENT": 5.0,
}

# Novelty is supportive evidence, not the definition of importance.
NOVELTY_COMPONENT_SCORE = {
    "NEW_EVENT": 10.0,
    "FOLLOW_UP": 8.0,
    "CONFIRMATION": 6.0,
    "REHASH": 3.0,
    "MARKET_REACTION": 0.0,
}

# Source reliability is capped at 5 so an official but routine filing cannot dominate.
SOURCE_SCORE = {
    "DART": 5.0,
    "KIND": 5.0,
    "MOTIR": 5.0,
    "MSIT": 5.0,
    "MCEE": 5.0,
    "MFDS": 5.0,
    "FSC": 5.0,
}

GRADE_SCORE = {
    "S": 5.0,
    "A": 4.0,
    "B": 3.0,
    "C": 2.0,
}

MONEY_RE = re.compile(r"(?:조원|억원|만원|달러|원)$", re.I)
CAPACITY_RE = re.compile(r"(?:GWh|MWh|kWh|GW|MW|kW|PB|TB)$", re.I)
PERCENT_RE = re.compile(r"(?:%|퍼센트)$", re.I)
QUANTITY_RE = re.compile(r"(?:개사|호기|척|대|개|건|명|기|곳|종|회)$", re.I)
DURATION_RE = re.compile(r"(?:개월|년|주)$", re.I)
CLINICAL_RE = re.compile(r"[123]상$", re.I)


def direct_company_score(event: ScoreInput) -> tuple[float, str]:
    # 15 points maximum. Directness matters, but less than the event itself.
    if event.stock_codes:
        return 15.0, "listed ticker directly identified"
    if event.companies:
        return 13.0, "named company directly identified"
    if event.event_type in POLICY_OR_SECTOR_EVENT_TYPES and event.original_source_id in OFFICIAL_GOV_SOURCES:
        return 8.0, "official policy/sector event without direct company"
    return 4.0, "event has no direct company/ticker"


def event_certainty_score(event: ScoreInput) -> tuple[float, str]:
    score = CERTAINTY_SCORE.get(event.event_stage, 8.0)
    return score, f"stage={event.event_stage}"


def financial_impact_score(event: ScoreInput) -> tuple[float, str]:
    # Column name is kept for DB/backward compatibility; semantics are catalyst importance.
    score = EVENT_IMPORTANCE_SCORE.get(event.event_type, 12.0)
    return score, f"event_importance={event.event_type}"


def quantification_score(event: ScoreInput) -> tuple[float, str]:
    if not event.numbers:
        return 0.0, "no meaningful numeric fact"

    categories = set()
    best = 0.0
    for value in event.numbers:
        text = str(value).strip()
        if MONEY_RE.search(text):
            categories.add("money")
            best = max(best, 15.0)
        elif CAPACITY_RE.search(text):
            categories.add("capacity")
            best = max(best, 14.0)
        elif PERCENT_RE.search(text):
            categories.add("percent")
            best = max(best, 13.0)
        elif QUANTITY_RE.search(text):
            categories.add("quantity")
            best = max(best, 11.0)
        elif CLINICAL_RE.search(text):
            categories.add("clinical_phase")
            best = max(best, 9.0)
        elif DURATION_RE.search(text):
            categories.add("duration")
            best = max(best, 7.0)
        else:
            categories.add("other")
            best = max(best, 5.0)

    if len(categories) >= 2:
        best = min(15.0, best + 1.0)
    return best, "numeric=" + ",".join(sorted(categories))


def novelty_component_score(event: ScoreInput) -> tuple[float, str]:
    score = NOVELTY_COMPONENT_SCORE.get(event.novelty_status, 0.0)
    return score, f"novelty={event.novelty_status}"


def source_reliability_score(event: ScoreInput) -> tuple[float, str]:
    source_score = SOURCE_SCORE.get(event.original_source_id, 0.0)
    grade_score = GRADE_SCORE.get((event.source_grade or "").upper(), 0.0)
    score = max(source_score, grade_score, 1.0 if event.original_source_id else 0.0)
    return score, f"source={event.original_source_id or 'UNKNOWN'},grade={event.source_grade or 'UNKNOWN'}"


def multi_source_score(event: ScoreInput) -> tuple[float, str]:
    if event.source_count >= 3:
        return 5.0, f"source_count={event.source_count}"
    if event.source_count >= 2:
        return 4.0, f"source_count={event.source_count}"
    if event.confirmation_count >= 1:
        return 3.0, f"confirmation_count={event.confirmation_count}"
    return 0.0, "single source without confirmation"


def status_from_score(score: float) -> str:
    if score >= 85:
        return "STRONG"
    if score >= 70:
        return "CONFIRMED"
    if score >= 55:
        return "WATCH"
    return "REJECT"
