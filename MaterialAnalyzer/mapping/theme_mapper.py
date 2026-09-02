from __future__ import annotations

import csv
from pathlib import Path

from ..analysis_models import ThemeMatch
from ..schedule_models import ScheduleItem


class ThemeMapper:
    """Map schedule text to themes using an editable keyword dictionary.

    V1 is deterministic and evidence-based. LLM inference is intentionally not used
    yet; unmatched schedules remain unmatched instead of inventing a theme.
    """

    def __init__(self, keyword_file: Path) -> None:
        self.keyword_file = keyword_file
        self.rules = self._load(keyword_file)

    def map(self, schedule: ScheduleItem) -> list[ThemeMatch]:
        text = f"{schedule.title} {schedule.summary} {schedule.query} {schedule.category}".lower()
        matches: list[ThemeMatch] = []

        for theme, keywords in self.rules:
            hit = tuple(keyword for keyword in keywords if keyword.lower() in text)
            if not hit:
                continue
            longest = max(len(keyword) for keyword in hit)
            confidence = min(0.99, 0.68 + min(len(hit), 3) * 0.08 + (0.07 if longest >= 5 else 0.0))
            matches.append(
                ThemeMatch(
                    theme=theme,
                    confidence=round(confidence, 2),
                    matched_keywords=hit,
                    match_type="KEYWORD",
                )
            )

        matches.sort(key=lambda row: (-row.confidence, row.theme))
        return matches

    @staticmethod
    def _load(path: Path) -> list[tuple[str, tuple[str, ...]]]:
        if not path.exists():
            return []
        out: list[tuple[str, tuple[str, ...]]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                enabled = str(row.get("enabled", "1")).strip().lower()
                if enabled in {"0", "false", "n", "no"}:
                    continue
                theme = str(row.get("theme", "")).strip()
                keywords = tuple(
                    keyword.strip()
                    for keyword in str(row.get("keywords", "")).split("|")
                    if keyword.strip()
                )
                if theme and keywords:
                    out.append((theme, keywords))
        return out
