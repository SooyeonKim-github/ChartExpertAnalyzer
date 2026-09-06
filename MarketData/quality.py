from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

QUALITY_OK = "OK"
QUALITY_SUSPECT = "SUSPECT"
QUALITY_INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class PriceQualitySnapshot:
    status: str
    max_abs_daily_return_pct: float | None
    large_jump_count: int
    largest_jump_date: str | None
    jump_threshold_pct: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def assess_price_quality(df: pd.DataFrame, *, jump_threshold_pct: float = 35.0, as_of=None, start=None, end=None) -> PriceQualitySnapshot:
    """Engineering-only continuity check; never a trading filter."""
    if jump_threshold_pct <= 0:
        raise ValueError("jump_threshold_pct must be > 0")
    if df is None or df.empty or "close" not in df.columns:
        return PriceQualitySnapshot(QUALITY_INSUFFICIENT,None,0,None,float(jump_threshold_pct),"no close history")
    close = pd.to_numeric(df["close"], errors="coerce")
    close.index = pd.to_datetime(df.index, errors="coerce")
    close = close[~close.index.isna()].dropna().sort_index()
    close = close[~close.index.duplicated(keep="last")]
    close = close[close.gt(0)]
    if as_of is not None:
        close = close[close.index.normalize() <= pd.Timestamp(as_of).normalize()]
    if start is not None:
        close = close[close.index.normalize() >= pd.Timestamp(start).normalize()]
    if end is not None:
        close = close[close.index.normalize() <= pd.Timestamp(end).normalize()]
    if len(close) < 2:
        return PriceQualitySnapshot(QUALITY_INSUFFICIENT,None,0,None,float(jump_threshold_pct),"fewer than 2 closes")
    ret = close.pct_change(fill_method=None) * 100.0
    abs_ret = ret.abs().dropna()
    if abs_ret.empty:
        return PriceQualitySnapshot(QUALITY_INSUFFICIENT,None,0,None,float(jump_threshold_pct),"no daily returns")
    max_date = abs_ret.idxmax()
    max_abs = float(abs_ret.loc[max_date])
    jumps = abs_ret[abs_ret > float(jump_threshold_pct)]
    if len(jumps):
        return PriceQualitySnapshot(QUALITY_SUSPECT,max_abs,int(len(jumps)),pd.Timestamp(max_date).strftime("%Y-%m-%d"),float(jump_threshold_pct),f"{len(jumps)} close-to-close jump(s) above {jump_threshold_pct:.1f}%")
    return PriceQualitySnapshot(QUALITY_OK,max_abs,0,pd.Timestamp(max_date).strftime("%Y-%m-%d"),float(jump_threshold_pct),"no abnormal close-to-close discontinuity detected")
