from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
RESULT_DIR = PROJECT_ROOT / "results"
CACHE_DIR = PROJECT_ROOT / "cache"
DEFAULT_INFO_EXCEL = PROJECT_ROOT.parent / "SwingChartProbabilityAnalyzer" / "KOSPI_Info.xlsx"


@dataclass(frozen=True)
class MAConfig:
    """Moving-average lecture strategy configuration (V2).

    The lecture supplies the strategy structure. Thresholds that the lecture did
    not quantify remain explicit engineering parameters so they can be tuned by
    backtest without changing the strategy meaning.
    """

    short_ma_period: int = 20
    long_ma_period: int = 200
    min_history_bars: int = 220
    history_calendar_days: int = 520

    # Direction / regime
    slope_lookback_bars: int = 10
    flat_long_slope_abs_pct: float = 0.15

    # Squeeze setup (V2: setup/watch only, never enough by itself for CONFIRMED)
    squeeze_lookback_bars: int = 15
    squeeze_recent_bars: int = 5
    squeeze_gap_max_pct: float = 4.0
    squeeze_compression_ratio: float = 0.75

    # Breakout confirmation
    body_avg_period: int = 20
    long_body_ratio: float = 1.7
    prior_high_lookback_bars: int = 20

    # Pullback / reclaim
    pullback_lookback_bars: int = 8
    ma_touch_tolerance_pct: float = 2.0

    # Sideways / box
    cross_lookback_bars: int = 20
    sideways_cross_count: int = 4
    box_lookback_bars: int = 20
    box_breakout_buffer_pct: float = 0.3
    box_retest_lookback_bars: int = 5
    box_retest_tolerance_pct: float = 2.0
    box_retest_max_break_pct: float = 1.0

    # Risk
    max_ma20_distance_pct: float = 10.0

    # Classification. V1 backtest showed the best separation around stronger
    # timing and score cohorts, but V2 removes duplicated box/prior-high/retest
    # points before applying these thresholds.
    strong_confirmed_score: int = 80
    strong_timing_score: int = 70
    confirmed_score: int = 70
    confirmed_timing_score: int = 50
    watch_score: int = 50

    # Range backtest
    cooldown_bars: int = 10

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = MAConfig()
