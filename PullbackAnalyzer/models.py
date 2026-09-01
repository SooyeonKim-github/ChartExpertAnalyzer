from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImpulseContext:
    available: bool = False
    bar_pos: int = -1
    date: str = ""
    base_pos: int = -1
    base_date: str = ""
    base_price: float = float("nan")
    open_price: float = float("nan")
    high_price: float = float("nan")
    close_price: float = float("nan")
    return_pct: float = float("nan")
    volume_ratio: float = float("nan")
    body_atr: float = float("nan")
    breakout_level: float = float("nan")
    breakout: bool = False
    event_count: int = 0
    sequence: int = 0


@dataclass
class PullbackContext:
    available: bool = False
    bars: int = 0
    low_price: float = float("nan")
    low_pos: int = -1
    depth_pct: float = float("nan")
    retracement_ratio: float = float("nan")
    current_drawdown_pct: float = float("nan")
    sequence: int = 0
    correction_type: str = "NONE"
    period_correction: bool = False
    price_correction: bool = False
    higher_low: bool = False
    midpoint_broken: bool = False
    atr_contraction: bool = False
    range_contraction: bool = False
    price_stopping: bool = False
    volume_ratio_impulse: float = float("nan")
    volume_ratio_20: float = float("nan")
    high_volume_breakdown: bool = False


@dataclass
class SupportContext:
    nearest_name: str = ""
    nearest_level: float = float("nan")
    distance_pct: float = float("nan")
    confluence_count: int = 0
    touch_count: int = 0
    near_ma: bool = False
    near_price_level: bool = False
    bb_support: bool = False
    support_held: bool = False
    levels: dict[str, float] = field(default_factory=dict)


@dataclass
class MarketContext:
    available: bool = False
    regime: str = "unknown"
    market_ret20: float = float("nan")
    market_ret60: float = float("nan")
    market_above_ma60: bool = False
    rs20: float = float("nan")
    rs60: float = float("nan")
    down_day_hit_rate20: float = float("nan")
    rs_score: float = 50.0


@dataclass
class PullbackAnalysisResult:
    ticker: str
    name: str
    market: str
    requested_date: str
    actual_date: str
    status: str
    score: int
    timing_score: int
    primary_signal: str
    pullback_type: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    component_scores: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        row = {
            "Ticker": self.ticker,
            "Name": self.name,
            "Market": self.market,
            "Requested_Date": self.requested_date,
            "Actual_Date": self.actual_date,
            "Status": self.status,
            "Score": self.score,
            "Timing_Score": self.timing_score,
            "Primary_Signal": self.primary_signal,
            "Pullback_Type": self.pullback_type,
            "Reasons": " | ".join(self.reasons),
            "Warnings": " | ".join(self.warnings),
        }
        for key, value in self.component_scores.items():
            row[f"{key}_Score"] = value
        row.update(self.metrics)
        return row
