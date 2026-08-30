from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
RESULT_DIR = PROJECT_ROOT / "results"
CACHE_DIR = PROJECT_ROOT / "cache"

# Reuse the repository's current stock-universe workbook instead of duplicating a binary file.
# The analyzer itself does not reuse Swing's signal logic.
DEFAULT_INFO_EXCEL = PROJECT_ROOT.parent / "SwingChartProbabilityAnalyzer" / "KOSPI_Info.xlsx"


@dataclass(frozen=True)
class MAConfig:
    """Moving-average strategy configuration.

    Source-backed values:
    - long_ma_period=200: explicitly described in the lecture as the main direction line.
    - short_ma_period=20: the subtitle alternates between expressions that OCR as 20/22.
      We normalize the default to 20 for implementation, but keep it configurable.

    All percentage/window thresholds below are engineering thresholds needed to turn
    qualitative lecture language ("flat", "squeeze", "long candle", "too far") into
    deterministic code. They are not claimed to be numeric thresholds from the lecture.
    """

    short_ma_period: int = 20
    long_ma_period: int = 200
    min_history_bars: int = 220
    history_calendar_days: int = 520

    # Direction / regime
    slope_lookback_bars: int = 10
    flat_long_slope_abs_pct: float = 0.15

    # Squeeze
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
    box_retest_tolerance_pct: float = 2.0

    # Risk
    max_ma20_distance_pct: float = 10.0

    # Classification
    confirmed_score: int = 70
    watch_score: int = 50

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = MAConfig()
