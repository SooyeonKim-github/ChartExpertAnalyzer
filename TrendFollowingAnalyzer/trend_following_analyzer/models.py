from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StageScreenResult:
    scan_date: str
    ticker: str
    name: str
    market: str
    trading_value_rank: int
    close: float
    ma50: float | None
    ma150: float | None
    ma150_slope_pct: float | None
    close_vs_ma150_pct: float | None
    ma50_vs_ma150_pct: float | None
    stage: str
    trend_eligible: bool
    stage_core_pass: bool
    stage_experimental_slope_pass: bool
    stage_reason: str

    market_regime: str
    market_eligible: bool
    market_index_close: float | None
    market_index_ma50: float | None
    market_index_ma150: float | None
    market_index_ma150_slope_pct: float | None
    market_index_close_vs_ma150_pct: float | None
    market_index_ma50_vs_ma150_pct: float | None
    market_lecture_ma150_position_pass: bool
    market_lecture_ma150_slope_pass: bool
    market_experimental_slope_threshold_pass: bool
    market_experimental_ma50_alignment_pass: bool
    market_regime_reason: str

    market_breadth_status: str
    market_breadth_measurement: str
    market_breadth_universe_count: int
    market_breadth_eligible_count: int
    market_breadth_coverage_ratio: float | None
    market_new_high_52w_count: int
    market_new_low_52w_count: int
    market_new_high_52w_ratio: float | None
    market_new_low_52w_ratio: float | None
    market_new_high_low_spread: float | None
    market_breadth_5d_avg: float | None
    market_breadth_20d_avg: float | None
    market_breadth_5d_change: float | None
    market_breadth_20d_change: float | None
    market_breadth_direction: str
    market_breadth_snapshot_dates_loaded: int
    market_breadth_snapshot_dates_expected: int
    market_breadth_snapshot_date_coverage_ratio: float | None
    market_breadth_filter_applied: bool

    lecture_core_pass: bool
    experimental_filters_applied: bool

    def to_dict(self) -> dict:
        return asdict(self)
