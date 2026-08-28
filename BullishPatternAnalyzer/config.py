from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UniverseConfig:
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    top_n: int = 100
    min_history_bars: int = 140
    history_calendar_days: int = 420
    market_cap_sort: bool = True


@dataclass(frozen=True)
class PatternConfig:
    swing_order: int = 3
    triangle_lookback: int = 70
    wedge_lookback: int = 80
    w_lookback: int = 100
    ihs_lookback: int = 130
    bull_flag_lookback: int = 45
    flat_resistance_tolerance_pct: float = 0.035
    triangle_min_rising_low_pct: float = 0.01
    wedge_min_width_shrink: float = 0.25
    w_bottom_tolerance_pct: float = 0.05
    w_min_separation_bars: int = 5
    w_max_separation_bars: int = 60
    w_ma20_max_distance_pct: float = 0.06
    w_decline_volume_good_ratio: float = 0.85
    ihs_shoulder_tolerance_pct: float = 0.08
    ihs_head_depth_min_pct: float = 0.02
    bull_flag_pole_days: int = 8
    bull_flag_flag_days: int = 12
    bull_flag_min_pole_return_pct: float = 0.08
    bull_flag_max_pullback_pct: float = 0.10
    bull_flag_volume_contraction_ratio: float = 0.85


@dataclass(frozen=True)
class ConfirmationConfig:
    breakout_min_pct: float = 0.002
    breakout_lookback_bars: int = 5
    breakout_volume_ratio_good: float = 1.15
    breakout_volume_ratio_strong: float = 1.60
    retest_tolerance_pct: float = 0.025
    retest_lookback_bars: int = 7
    chase_medium_atr: float = 1.5
    chase_high_atr: float = 2.5
    entry_risk_medium_pct: float = 0.05
    entry_risk_high_pct: float = 0.08


@dataclass(frozen=True)
class VolumeFilterConfig:
    enabled: bool = True
    breakout_min_ratio: float = 1.15
    breakout_strong_ratio: float = 1.60
    contraction_window: int = 5
    reference_window: int = 20
    contraction_max_ratio: float = 0.85
    oscillator_short: int = 5
    oscillator_long: int = 20
    require_positive_oscillator: bool = False
    distribution_min_ratio: float = 1.30


@dataclass(frozen=True)
class CandleConfig:
    momentum_body_ratio_min: float = 0.60
    momentum_close_location_min: float = 0.75
    pin_lower_wick_ratio_min: float = 0.45
    pin_body_ratio_max: float = 0.35
    long_upper_wick_ratio_min: float = 0.40
    narrow_body_ratio_max: float = 0.25
    high_zone_lookback: int = 60
    high_zone_ratio: float = 0.90


@dataclass(frozen=True)
class ScoreConfig:
    candidate_selection_min: float = 70.0
    entry_timing_min: float = 70.0
    watch_selection_min: float = 60.0


@dataclass(frozen=True)
class BacktestConfig:
    event_cooldown_sessions: int = 10
    daily_candidate_top_n: int = 20
    entry_mode: str = "NEXT_OPEN"


@dataclass(frozen=True)
class MarketConfig:
    index_tickers: dict[str, str] = field(default_factory=lambda: {"KOSPI": "1001", "KOSDAQ": "2001"})
    crash_drawdown_pct: float = -0.10
    weak_drawdown_pct: float = -0.06
    recent_window_bars: int = 20


UNIVERSE = UniverseConfig()
PATTERN = PatternConfig()
CONFIRMATION = ConfirmationConfig()
VOLUME_FILTER = VolumeFilterConfig()
CANDLE = CandleConfig()
SCORE = ScoreConfig()
BACKTEST = BacktestConfig()
MARKET = MarketConfig()
FORWARD_BARS: tuple[int, ...] = (1, 3, 5, 10, 20, 40, 60)
