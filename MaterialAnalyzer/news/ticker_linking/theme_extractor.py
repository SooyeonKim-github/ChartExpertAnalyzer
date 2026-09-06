from __future__ import annotations

import re

from .models import ThemeMatch


SPACE_RE = re.compile(r"\s+")


class ThemeExtractor:
    """Deterministic keyword/event-type theme extraction. No embeddings/LLM."""

    def __init__(self, reference_data):
        self.rules = reference_data.theme_rules

    def extract(self, event_type: str, title: str, summary: str) -> list[ThemeMatch]:
        text = SPACE_RE.sub(" ", f"{title or ''} {summary or ''}").casefold().strip()
        event_type = (event_type or "UNKNOWN").upper()
        matches: list[ThemeMatch] = []

        for rule in self.rules:
            if rule.event_types and event_type not in rule.event_types:
                continue
            hits = tuple(keyword for keyword in rule.keywords if keyword.casefold() in text)
            if not hits:
                continue
            confidence = rule.confidence
            if len(hits) >= 2:
                confidence = min(0.99, confidence + 0.05)
            if any(len(hit) >= 5 for hit in hits):
                confidence = min(0.99, confidence + 0.03)
            matches.append(ThemeMatch(
                theme=rule.theme,
                confidence=round(confidence, 2),
                matched_keywords=hits,
                rule=rule,
            ))

        matches.sort(key=lambda row: (-row.confidence, row.theme))
        return matches
