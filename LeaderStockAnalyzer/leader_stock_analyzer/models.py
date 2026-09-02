from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SignalScore:
    score: float | None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimingScore:
    score: float
    entry_state: str
    source: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LeaderResult:
    scan_date: str
    ticker: str
    name: str
    market: str
    status: str
    leader_score: float
    timing_score: float
    market_leader_rank: int
    trading_value_rank: int
    price: float
    return_pct: float
    trading_value: float
    money_flow_score: float | None
    price_strength_score: float | None
    daily_position_score: float | None
    intraday_strength_score: float | None
    relative_strength_score: float | None
    ma_structure_score: float | None
    chase_risk: float
    entry_state: str
    timing_source: str
    intraday_available: bool
    high_10d_break: bool
    high_20d_break: bool
    high_52d_break: bool
    previous_high_break: bool
    close_20d_high: bool
    volume_ratio_20: float | None
    market_relative_strength: float | None
    signal: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("details", None)
        return out
