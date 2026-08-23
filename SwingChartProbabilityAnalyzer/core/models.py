from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Pivot:
    pos: int
    price: float
    kind: str


@dataclass
class Channel:
    high1_pos: int
    high1_price: float
    high2_pos: int
    high2_price: float
    low_anchor_pos: int
    low_anchor_price: float
    slope: float
    upper_intercept: float
    lower_intercept: float
    coverage: float
    high_touches: int
    low_touches: int

    def upper(self, pos: int) -> float:
        return self.slope * pos + self.upper_intercept

    def lower(self, pos: int) -> float:
        return self.slope * pos + self.lower_intercept

    def mid(self, pos: int) -> float:
        return (self.upper(pos) + self.lower(pos)) / 2.0

    def position(self, pos: int, price: float) -> float:
        width = self.upper(pos) - self.lower(pos)
        if width <= 0:
            return float("nan")
        return (price - self.lower(pos)) / width


@dataclass
class AnalysisResult:
    ticker: str
    name: str
    target_date: str
    actual_date: str
    status: str
    score: int
    primary_signal: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    probabilities: dict = field(default_factory=dict)
    channel: Optional[Channel] = None

    def to_row(self) -> dict:
        row = {
            "Ticker": self.ticker, "Name": self.name, "Target_Date": self.target_date,
            "Actual_Date": self.actual_date, "Status": self.status, "Score": self.score,
            "Primary_Signal": self.primary_signal,
            "Reasons": " | ".join(self.reasons), "Warnings": " | ".join(self.warnings),
        }
        row.update(self.metrics)
        row.update(self.probabilities)
        return row
