from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ThemeMatch:
    theme: str
    confidence: float
    matched_keywords: tuple[str, ...]
    match_type: str = "KEYWORD"


@dataclass(frozen=True)
class StockThemeMatch:
    theme: str
    ticker: str
    name: str
    relevance: float
    relation_type: str
    reason: str = ""

    @property
    def stock_theme_score(self) -> float:
        return round(max(0.0, min(self.relevance, 1.0)) * 100.0, 2)


@dataclass(frozen=True)
class ScheduleImportanceResult:
    schedule_score: float
    priority: str
    authority_score: float
    novelty_score: float
    money_score: float
    policy_score: float
    theme_clarity_score: float
    event_certainty_score: float
    novelty_status: str
    similar_history_count: int
    money_amount_krw: int
    reason: str


@dataclass
class ScheduleAnalysisRow:
    scan_date: str
    event_date: str
    event_time: str
    schedule_kind: str
    title: str
    schedule_score: float
    priority: str
    authority_score: float
    novelty_score: float
    money_score: float
    policy_score: float
    theme_clarity_score: float
    event_certainty_score: float
    novelty_status: str
    similar_history_count: int
    money_amount_krw: int
    theme: str
    theme_confidence: float
    theme_match_type: str
    matched_keywords: str
    ticker: str
    name: str
    stock_theme_score: float | None
    relation_type: str
    reason: str
    source: str
    url: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
