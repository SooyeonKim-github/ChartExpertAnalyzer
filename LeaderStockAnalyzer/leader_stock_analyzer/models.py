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
class BreakoutQualityResult:
    score: float | None
    label: str
    available: bool
    breakout_type: str | None
    breakout_reference: float | None
    breakout_distance_pct: float | None = None
    close_location_value: float | None = None
    upper_wick_ratio: float | None = None
    volume_ratio_20: float | None = None
    turnover_ratio_20: float | None = None
    gap_pct: float | None = None
    breakout_hold_pct: float | None = None
    pre_breakout_distance_pct: float | None = None
    volatility_contraction_ratio: float | None = None
    false_breakout: bool = False
    exhaustion_risk: bool = False
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

    # Breakout quality is independent of the 100-point Leader Score.
    breakout_quality_available: bool = False
    breakout_type: str | None = None
    breakout_reference: float | None = None
    breakout_quality_score: float | None = None
    breakout_quality_label: str = "NO_BREAKOUT"
    breakout_distance_pct: float | None = None
    close_location_value: float | None = None
    upper_wick_ratio: float | None = None
    turnover_ratio_20: float | None = None
    gap_pct: float | None = None
    breakout_hold_pct: float | None = None
    pre_breakout_distance_pct: float | None = None
    volatility_contraction_ratio: float | None = None
    false_breakout_flag: bool = False
    breakout_exhaustion_risk: bool = False

    # Sector context. These do not change the original 100-point Leader Score.
    sector: str | None = None
    sector_context_available: bool = False
    sector_context_reliable: bool = False
    stock_return_5d: float | None = None
    stock_return_20d: float | None = None
    sector_ret_5d: float | None = None
    sector_ret_20d: float | None = None
    sector_rs_5d: float | None = None
    sector_rs_20d: float | None = None
    stock_vs_sector_rs_5d: float | None = None
    stock_vs_sector_rs_20d: float | None = None
    sector_strength_score: float | None = None
    sector_market_rank: int = 0
    sector_leader_score: float | None = None
    sector_leader_rank: int = 0
    sector_member_count: int = 0
    sector_breadth: float | None = None
    sector_turnover_ratio: float | None = None

    # Leadership persistence reconstructed from recent trading-value ranks.
    persistence_available: bool = False
    leader_persistence_score: float | None = None
    leader_persistence_level: str = "UNKNOWN"
    turnover_rank_avg_5d: float | None = None
    turnover_top20_days_5d: int = 0
    turnover_top50_days_10d: int = 0
    strong_return_days_5d: int = 0
    leader_type: str = "NORMAL"

    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("details", None)
        return out
