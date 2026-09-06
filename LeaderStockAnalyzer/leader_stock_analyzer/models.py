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

    # Emerging Leader / Rank Velocity. Independent from the original Leader Score.
    emerging_available: bool = False
    emerging_raw_score: float | None = None
    emerging_leader_score: float | None = None
    emerging_label: str = "UNKNOWN"
    emerging_overheat_penalty: float = 0.0
    emerging_overheat_flags: str = ""
    momentum_spike_flag: bool = False
    emerging_rank_today: float | None = None
    emerging_rank_1d_ago: float | None = None
    emerging_rank_3d_ago: float | None = None
    emerging_rank_5d_ago: float | None = None
    rank_velocity_1d: float | None = None
    rank_velocity_3d: float | None = None
    rank_velocity_5d: float | None = None
    rank_percentile_velocity_5d: float | None = None
    rank_acceleration: float | None = None
    trading_value_ratio_5d: float | None = None
    trading_value_ratio_20d: float | None = None
    trading_value_acceleration: float | None = None
    emerging_rs_3d: float | None = None
    emerging_rs_5d: float | None = None
    emerging_rs_acceleration: float | None = None
    emerging_rank_score: float | None = None
    emerging_money_flow_score: float | None = None
    emerging_rs_score: float | None = None
    emerging_freshness_score: float | None = None
    true_emerging_flag: bool = False
    strong_emerging_flag: bool = False

    # Exhaustion Risk V1.1. Observational only until range backtests validate it.
    exhaustion_risk_available: bool = False
    exhaustion_risk_score: float | None = None
    exhaustion_risk_label: str = "UNKNOWN"
    exhaustion_overextension_score: float | None = None
    exhaustion_deceleration_score: float | None = None
    exhaustion_distribution_score: float | None = None
    exhaustion_money_flow_decay_score: float | None = None
    exhaustion_structure_score: float | None = None
    exhaustion_flags: str = ""
    exhaustion_return_5d: float | None = None
    exhaustion_return_10d: float | None = None
    price_momentum_deceleration: float | None = None
    rs_deceleration: float | None = None
    rank_reversal_3d: float | None = None
    rank_reversal_5d: float | None = None
    trading_value_decay_ratio: float | None = None
    exhaustion_distance_ma10_pct: float | None = None
    exhaustion_distance_ma20_pct: float | None = None
    atr_extension: float | None = None
    exhaustion_ma10_slope_5d_pct: float | None = None
    exhaustion_ma20_slope_5d_pct: float | None = None
    exhaustion_drawdown_20d_pct: float | None = None
    exhaustion_below_ma10: bool = False
    exhaustion_below_ma20: bool = False
    exhaustion_momentum_3d: float | None = None
    exhaustion_momentum_peak_10d: float | None = None
    exhaustion_momentum_drop_from_peak: float | None = None
    exhaustion_leader_score_peak_5obs: float | None = None
    exhaustion_leader_score_decay: float | None = None
    exhaustion_rs_current: float | None = None
    exhaustion_rs_peak_5obs: float | None = None
    exhaustion_rs_decay_from_peak: float | None = None
    exhaustion_persistence_peak_5obs: float | None = None
    exhaustion_persistence_decay_from_peak: float | None = None
    exhaustion_distance_ma10_decay_5d: float | None = None
    exhaustion_distance_ma20_decay_5d: float | None = None

    # Leader Lifecycle V2. Lifecycle is observational and does not yet modify
    # Leader Score or confirmation status.
    lifecycle_available: bool = False
    lifecycle_state: str = "UNKNOWN"
    lifecycle_prev_state: str = "UNKNOWN"
    lifecycle_transition: bool = False
    lifecycle_days_in_state: int = 0
    lifecycle_observed_days: int = 0
    lifecycle_state_start_date: str = ""
    lifecycle_reason: str = ""
    lifecycle_drawdown_20d_pct: float | None = None
    lifecycle_below_ma20: bool = False
    lifecycle_exhaustion_flags: int = 0
    lifecycle_broken_flags: int = 0

    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("details", None)
        return out
