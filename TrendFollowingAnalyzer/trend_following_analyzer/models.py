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
    market_breadth_source_mode: str
    market_breadth_membership_mode: str
    market_breadth_source_ticker_count: int
    market_breadth_failed_tickers: int
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
    market_intraday_status: str
    market_intraday_measurement: str
    market_gap_return_pct: float | None
    market_open_close_return_pct: float | None
    market_close_return_pct: float | None
    market_close_location_value: float | None
    market_recovery_strength_pct: float | None
    market_fade_strength_pct: float | None
    market_intraday_label: str
    market_experimental_intraday_strength_score: float | None
    market_weak_open_strong_close_5d_ratio: float | None
    market_weak_open_strong_close_20d_ratio: float | None
    market_strong_open_weak_close_5d_ratio: float | None
    market_strong_open_weak_close_20d_ratio: float | None
    market_strong_close_5d_ratio: float | None
    market_strong_close_20d_ratio: float | None
    market_weak_close_5d_ratio: float | None
    market_weak_close_20d_ratio: float | None
    market_intraday_direction: str
    market_intraday_filter_applied: bool
    rs_status: str
    rs_measurement: str
    rs_percentile_scope: str
    stock_return_20d_pct: float | None
    benchmark_return_20d_pct: float | None
    rs_20d_pct: float | None
    stock_return_60d_pct: float | None
    benchmark_return_60d_pct: float | None
    rs_60d_pct: float | None
    rs_percentile_20d: float | None
    rs_percentile_60d: float | None
    rs_percentile_composite: float | None
    rs_label: str
    rs_experimental_20d_outperform_pass: bool
    rs_experimental_60d_outperform_pass: bool
    rs_experimental_percentile_pass: bool
    rs_filter_applied: bool
    base_status: str
    base_measurement: str
    base_start_date: str | None
    base_end_date: str | None
    base_duration_sessions: int | None
    base_high_date: str | None
    base_high: float | None
    base_low_date: str | None
    base_low: float | None
    base_depth_pct: float | None
    base_current_vs_high_pct: float | None
    base_atr_early_pct: float | None
    base_atr_late_pct: float | None
    base_atr_contraction_ratio: float | None
    base_range_early_pct: float | None
    base_range_late_pct: float | None
    base_range_contraction_ratio: float | None
    base_close_dispersion_pct: float | None
    base_experimental_quality_score: float | None
    base_experimental_depth_pass: bool
    base_experimental_end_near_high_pass: bool
    base_experimental_resistance_pass: bool
    base_filter_applied: bool
    prior_advance_status: str
    prior_advance_measurement: str
    prior_advance_anchor_mode: str
    prior_advance_anchor_is_base: bool
    prior_advance_lookback_sessions: int
    prior_advance_recent_window_sessions: int
    prior_advance_low_date: str | None
    prior_advance_peak_date: str | None
    prior_advance_low: float | None
    prior_advance_peak: float | None
    prior_advance_pct: float | None
    prior_advance_duration_sessions: int | None
    prior_advance_sessions_from_peak_to_anchor: int | None
    prior_advance_peak_to_base_sessions: int | None
    prior_advance_current_vs_peak_pct: float | None
    prior_advance_peak_vs_ma150_pct: float | None
    prior_advance_drawdown_to_base_low_pct: float | None
    prior_advance_retention_ratio: float | None
    prior_advance_current_retention_ratio: float | None
    prior_return_60d_pct: float | None
    prior_return_120d_pct: float | None
    prior_advance_experimental_min_pass: bool
    prior_advance_filter_applied: bool
    lecture_core_pass: bool
    experimental_filters_applied: bool

    def to_dict(self) -> dict:
        return asdict(self)
