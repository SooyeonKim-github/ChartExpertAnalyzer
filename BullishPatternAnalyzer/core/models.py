from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PatternType(str, Enum):
    ASCENDING_TRIANGLE = "ASCENDING_TRIANGLE"
    SYMMETRICAL_TRIANGLE = "SYMMETRICAL_TRIANGLE"
    FALLING_WEDGE = "FALLING_WEDGE"
    BULL_FLAG = "BULL_FLAG"
    W_PATTERN = "W_PATTERN"
    INVERSE_HEAD_SHOULDERS = "INVERSE_HEAD_SHOULDERS"


class PatternCategory(str, Enum):
    CONTINUATION = "CONTINUATION"
    REVERSAL = "REVERSAL"
    DIRECTIONAL = "DIRECTIONAL"


class PatternState(str, Enum):
    FORMING = "FORMING"
    WATCH = "WATCH"
    BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
    RETEST = "RETEST"
    ENTRY_READY = "ENTRY_READY"
    INVALIDATED = "INVALIDATED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class MarketRegime(str, Enum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    WEAK = "WEAK"
    CRASH = "CRASH"
    UNKNOWN = "UNKNOWN"


@dataclass
class PatternDetection:
    pattern_type: PatternType
    category: PatternCategory
    state: PatternState
    structure_score: float
    breakout_level: float | None = None
    support_level: float | None = None
    stop_level: float | None = None
    anchors: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    date: str
    ticker: str
    name: str
    market: str
    pattern_type: PatternType
    pattern_category: PatternCategory
    pattern_state: PatternState
    structure_score: float
    breakout_score: float
    volume_score: float
    candle_score: float
    momentum_score: float
    retest_score: float
    selection_score: float
    timing_score: float
    volume_filter_pass: bool
    candle_signal: str
    chase_risk: RiskLevel
    entry_risk: RiskLevel
    market_regime: MarketRegime
    breakout_level: float | None
    support_level: float | None
    stop_level: float | None
    current_price: float
    breakout_price: float | None
    volume_ratio: float
    distance_from_breakout_pct: float | None
    bullish_divergence: bool
    retest_valid: bool
    signal_reason: str
    risk_reason: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        row = asdict(self)
        for key in ("pattern_type", "pattern_category", "pattern_state", "chase_risk", "entry_risk", "market_regime"):
            value = row[key]
            row[key] = value.value if hasattr(value, "value") else value
        metrics = row.pop("metrics", {})
        for key, value in metrics.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                row[f"metric_{key}"] = value
        return row
