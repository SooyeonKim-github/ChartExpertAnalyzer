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

    lecture_core_pass: bool
    experimental_filters_applied: bool

    def to_dict(self) -> dict:
        return asdict(self)
