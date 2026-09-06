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
    stage_reason: str

    def to_dict(self) -> dict:
        return asdict(self)
