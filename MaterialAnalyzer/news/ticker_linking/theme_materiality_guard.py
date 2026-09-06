from __future__ import annotations

import re

from .models import LinkInput, ThemeMatch, ThemeMaterialityResult


MEANINGFUL_NUMBER_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:조원|억원|만원|달러|%|퍼센트|GW|MW|GWh|MWh|kW|개|건|대|척|명|곳|종|회)",
    re.I,
)

MATERIAL_EVENT_TYPES = {
    "GOV_POLICY", "CAPEX", "INVESTMENT", "ORDER_CONTRACT", "SUBSIDY", "REGULATION",
    "AI_DATACENTER", "SEMICONDUCTOR", "SECONDARY_BATTERY", "NUCLEAR", "DEFENSE",
    "SHIPBUILDING", "SUPPLY", "SHORTAGE", "PRODUCT", "APPROVAL",
}

STAGE_BONUS = {
    "CONFIRMED": 10.0,
    "APPROVED": 10.0,
    "STARTED": 10.0,
    "COMPLETED": 10.0,
    "PLANNED": 5.0,
    "ANNOUNCED": 3.0,
}


class ThemeMaterialityGuard:
    """Decide whether a recognized theme is strong enough to fan out to tradable tickers."""

    def evaluate(self, event: LinkInput, match: ThemeMatch) -> ThemeMaterialityResult:
        rule = match.rule
        text = f"{event.event_title or ''} {event.event_summary or ''}".casefold()
        strong_hits = tuple(k for k in (rule.strong_keywords if rule else ()) if k.casefold() in text)
        weak_hits = tuple(k for k in (rule.weak_keywords if rule else ()) if k.casefold() in text)

        score = 30.0
        reasons = ["theme_match=30"]

        if event.event_type in MATERIAL_EVENT_TYPES:
            score += 15
            reasons.append("material_event_type=+15")

        if strong_hits:
            score += 25
            reasons.append("strong_trigger=+25")
            if len(strong_hits) >= 2:
                score += 10
                reasons.append("multiple_strong=+10")

        if MEANINGFUL_NUMBER_RE.search(text):
            score += 10
            reasons.append("meaningful_number=+10")

        stage_bonus = STAGE_BONUS.get((event.event_stage or "").upper(), 0.0)
        if stage_bonus:
            score += stage_bonus
            reasons.append(f"stage=+{stage_bonus:g}")

        if weak_hits:
            score -= 35
            reasons.append("weak_trigger=-35")
            if len(weak_hits) >= 2:
                score -= 10
                reasons.append("multiple_weak=-10")

        score = max(0.0, min(100.0, score))
        threshold = rule.min_materiality if rule else 70.0
        return ThemeMaterialityResult(
            theme=match.theme,
            score=round(score, 2),
            eligible=score >= threshold,
            strong_hits=strong_hits,
            weak_hits=weak_hits,
            reason=",".join(reasons) + f",threshold={threshold:g}",
        )
