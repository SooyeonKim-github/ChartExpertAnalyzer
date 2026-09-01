from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
RESULT_DIR = PROJECT_ROOT / "results"
CACHE_DIR = PROJECT_ROOT / "cache"
DEFAULT_INFO_EXCEL = PROJECT_ROOT.parent / "SwingChartProbabilityAnalyzer" / "KOSPI_Info.xlsx"


@dataclass(frozen=True)
class PullbackConfig:
    """Lecture-derived pullback analyzer V1 configuration."""

    min_history_bars: int = 230
    history_calendar_days: int = 620
    ma_periods: tuple[int, ...] = (5, 10, 20, 60, 120, 224)
    atr_period: int = 14
    volume_period: int = 20
    bb_period: int = 20
    bb_std: float = 2.0

    impulse_search_bars: int = 70
    impulse_base_lookback: int = 30
    impulse_min_age_bars: int = 2
    impulse_max_age_bars: int = 35
    impulse_min_return_pct: float = 10.0
    impulse_strong_return_pct: float = 20.0
    impulse_volume_ratio_min: float = 1.20
    impulse_volume_ratio_strong: float = 2.0
    impulse_body_atr_min: float = 0.60
    impulse_breakout_lookback: int = 20
    impulse_event_separation_bars: int = 5

    ideal_retracement_max: float = 0.33
    acceptable_retracement_max: float = 0.45
    hard_retracement_max: float = 0.55
    period_correction_min_bars: int = 5
    shallow_drawdown_pct: float = 10.0
    price_stop_lookback_bars: int = 3

    support_near_pct: float = 2.0
    support_max_pct: float = 4.0
    support_touch_tolerance_pct: float = 1.5
    support_touch_lookback_bars: int = 20
    support_break_pct: float = 2.0

    local_high_lookback_bars: int = 5
    confirmation_volume_ratio: float = 1.10
    reclaim_tolerance_pct: float = 0.5

    ma_slope_lookback_bars: int = 10
    high_volume_breakdown_ratio: float = 1.50
    long_bear_body_atr: float = 1.0
    decisive_ma60_break_pct: float = 3.0
    major_low_lookback_bars: int = 20

    max_ma20_extension_pct: float = 12.0
    max_stop_distance_pct: float = 8.0

    confirmed_score: int = 70
    confirmed_timing_score: int = 60
    watch_score: int = 50
    min_impulse_score_confirmed: int = 8
    min_pullback_score_confirmed: int = 11
    min_volume_score_confirmed: int = 8
    min_confirmation_score_confirmed: int = 5

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = PullbackConfig()
