from __future__ import annotations

import re

from .models import ScoreInput


OFFICIAL_GOV_SOURCES = {"MOTIR", "MSIT", "MCEE", "MFDS", "FSC"}
DISCLOSURE_SOURCES = {"DART", "KIND"}

POLICY_OR_SECTOR_EVENT_TYPES = {
    "GOV_POLICY", "SUBSIDY", "REGULATION", "AI", "AI_DATACENTER", "SEMICONDUCTOR",
    "SECONDARY_BATTERY", "DEFENSE", "NUCLEAR", "SHIPBUILDING", "BIO", "SUPPLY", "SHORTAGE",
}

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

FINANCIAL_IMPACT_SCORE = {
    "ORDER_CONTRACT": 15.0,
    "MNA": 15.0,
    "EARNINGS": 15.0,
    "GUIDANCE": 15.0,
    "PUBLIC_OFFER": 14.0,
    "RESTRUCTURING": 14.0,
    "CAPEX": 14.0,
    "INVESTMENT": 14.0,
    "ASSET_TRANSACTION": 14.0,
    "CAPITAL_RAISE": 13.0,
    "BUYBACK": 13.0,
    "VALUE_UP": 13.0,
    "CAPITAL_REDUCTION": 13.0,
    "APPROVAL": 13.0,
    "CLINICAL": 12.0,
    "DIVIDEND": 12.0,
    "TREASURY_STOCK_DISPOSAL": 12.0,
    "CONVERTIBLE_EXERCISE": 12.0,
    "INVESTMENT_DISPOSAL": 12.0,
    "DERIVATIVE_LOSS": 12.0,
    "PRICE_INCREASE": 12.0,
    "SHORTAGE": 12.0,
    "SANCTION": 12.0,
    "RECALL": 12.0,
    "GOV_POLICY": 12.0,
    "LITIGATION": 11.0,
    "TRADING_HALT": 11.0,
    "SUBSIDY": 11.0,
    "DEFENSE": 11.0,
    "NUCLEAR": 11.0,
    "AI_DATACENTER": 11.0,
    "PRODUCT": 11.0,
    "CONVERTIBLE_ADJUSTMENT": 10.0,
    "FINANCING": 10.0,
    "MATERIAL_MANAGEMENT": 10.0,
    "AI": 10.0,
    "SEMICONDUCTOR": 10.0,
    "SECONDARY_BATTERY": 10.0,
    "SHIPBUILDING": 10.0,
    "BIO": 10.0,
    "DEBT_GUARANTEE": 10.0,
    "SHARE_CONSOLIDATION": 9.0,
    "PARTNERSHIP": 9.0,
    "SUPPLY": 9.0,
    "REGULATION": 9.0,
    "PATENT": 8.0,
    "OWNERSHIP_CHANGE": 8.0,
    "CORPORATE_GOVERNANCE": 6.0,
    "MARKET_QUERY": 5.0,
    "IR_EVENT": 4.0,
}

NOVELTY_COMPONENT_SCORE = {
    "NEW_EVENT": 10.0,
    "FOLLOW_UP": 8.0,
    "CONFIRMATION": 5.0,
    "REHASH": 1.0,
    "MARKET_REACTION": 0.0,
}

SOURCE_SCORE = {
    "DART": 10.0,
    "KIND": 10.0,
    "MOTIR": 9.0,
    "MSIT": 9.0,
    "MCEE": 9.0,
    "MFDS": 9.0,
    "FSC": 9.0,
}

GRADE_SCORE = {
    "S": 9.0,
    "A": 7.0,
    "B": 5.0,
    "C": 3.0,
}

MONEY_RE = re.compile(r"(?:조원|억원|만원|달러|원)$", re.I)
CAPACITY_RE = re.compile(r"(?:GWh|MWh|kWh|GW|MW|kW|PB|TB)$", re.I)
PERCENT_RE = re.compile(r"(?:%|퍼센트)$", re.I)
QUANTITY_RE = re.compile(r"(?:개사|호기|척|대|개|건|명|기|곳|종|회)$", re.I)
DURATION_RE = re.compile(r"(?:개월|년|주)$", re.I)
CLINICAL_RE = re.compile(r"[123]상$", re.I)


def direct_company_score(event: ScoreInput) -> tuple[float, str]:
    if event.stock_codes:
        return 25.0, "listed ticker directly identified"
    if event.companies:
        return 22.0, "named company directly identified"
    if event.event_type in POLICY_OR_SECTOR_EVENT_TYPES and event.original_source_id in OFFICIAL_GOV_SOURCES:
        return 15.0, "official policy/sector event without direct company"
    return 8.0, "event has no direct company/ticker"


def event_certainty_score(event: ScoreInput) -> tuple[float, str]:
    score = CERTAINTY_SCORE.get(event.event_stage, 8.0)
    return score, f"stage={event.event_stage}"


def financial_impact_score(event: ScoreInput) -> tuple[float, str]:
    score = FINANCIAL_IMPACT_SCORE.get(event.event_type, 7.0)
    return score, f"event_type={event.event_type}"


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
    score = max(source_score, grade_score, 4.0 if event.original_source_id else 0.0)
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
