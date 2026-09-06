from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

RS_AVAILABLE = "AVAILABLE"
RS_INSUFFICIENT = "INSUFFICIENT"
WEAK_MARKET_RESILIENT = "WEAK_MARKET_RESILIENT"
CONSISTENT_OUTPERFORM = "CONSISTENT_OUTPERFORM"
MIXED_OUTPERFORMANCE = "MIXED_OUTPERFORMANCE"
UNDERPERFORM = "UNDERPERFORM"


@dataclass(frozen=True)
class RelativeStrengthSnapshot:
    market: str
    status: str
    measurement: str
    percentile_scope: str
    stock_return_20d_pct: float | None
    benchmark_return_20d_pct: float | None
    rs_20d_pct: float | None
    stock_return_60d_pct: float | None
    benchmark_return_60d_pct: float | None
    rs_60d_pct: float | None
    rs_label: str

    def to_dict(self) -> dict:
        return asdict(self)


def _float_or_none(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _normalize_close(df: pd.DataFrame, *, as_of=None) -> pd.Series:
    if df is None or df.empty or "close" not in df.columns:
        return pd.Series(dtype=float)
    out = pd.DataFrame({"close": pd.to_numeric(df["close"], errors="coerce")})
    out.index = pd.to_datetime(df.index, errors="coerce")
    out = out[~out.index.isna()]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out[out["close"].gt(0)].dropna()
    if as_of is not None:
        cutoff = pd.Timestamp(as_of).normalize()
        out = out[out.index.normalize() <= cutoff]
    return out["close"]


def _relative_window(aligned: pd.DataFrame, sessions: int) -> tuple[float | None, float | None, float | None]:
    if sessions <= 0:
        raise ValueError("sessions must be positive")
    if len(aligned) < sessions + 1:
        return None, None, None
    current = aligned.iloc[-1]
    base = aligned.iloc[-sessions - 1]
    stock_factor = float(current["stock"] / base["stock"])
    benchmark_factor = float(current["benchmark"] / base["benchmark"])
    stock_ret = (stock_factor - 1.0) * 100.0
    benchmark_ret = (benchmark_factor - 1.0) * 100.0
    rs = ((stock_factor / benchmark_factor) - 1.0) * 100.0
    return stock_ret, benchmark_ret, rs


def compute_relative_strength_snapshot(stock_df: pd.DataFrame, benchmark_df: pd.DataFrame, *, market: str, short_window: int = 20, long_window: int = 60, as_of=None) -> RelativeStrengthSnapshot:
    if short_window <= 0 or long_window <= 0 or short_window >= long_window:
        raise ValueError("RS windows must satisfy 0 < short_window < long_window")
    stock = _normalize_close(stock_df, as_of=as_of)
    benchmark = _normalize_close(benchmark_df, as_of=as_of)
    aligned = pd.concat([stock.rename("stock"), benchmark.rename("benchmark")], axis=1, join="inner").dropna()
    stock20, bench20, rs20 = _relative_window(aligned, short_window)
    stock60, bench60, rs60 = _relative_window(aligned, long_window)
    if rs20 is None or rs60 is None:
        status, label = RS_INSUFFICIENT, RS_INSUFFICIENT
    else:
        status = RS_AVAILABLE
        if bench20 is not None and bench20 <= 0 and rs20 > 0:
            label = WEAK_MARKET_RESILIENT
        elif rs20 > 0 and rs60 > 0:
            label = CONSISTENT_OUTPERFORM
        elif rs20 > 0 or rs60 > 0:
            label = MIXED_OUTPERFORMANCE
        else:
            label = UNDERPERFORM
    return RelativeStrengthSnapshot(market=str(market).upper(), status=status, measurement="PRICE_RATIO_VS_MARKET", percentile_scope="SAME_MARKET_WITHIN_SCREEN_TOP_N_TRADING_VALUE", stock_return_20d_pct=_float_or_none(stock20), benchmark_return_20d_pct=_float_or_none(bench20), rs_20d_pct=_float_or_none(rs20), stock_return_60d_pct=_float_or_none(stock60), benchmark_return_60d_pct=_float_or_none(bench60), rs_60d_pct=_float_or_none(rs60), rs_label=label)


def add_cross_sectional_rs_percentiles(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for source, target in [("rs_20d_pct", "rs_percentile_20d"), ("rs_60d_pct", "rs_percentile_60d")]:
        out[source] = pd.to_numeric(out.get(source), errors="coerce")
        if "market" in out.columns:
            out[target] = out.groupby("market", dropna=False)[source].rank(method="average", pct=True) * 100.0
        else:
            out[target] = out[source].rank(method="average", pct=True) * 100.0
    out["rs_percentile_composite"] = out[["rs_percentile_20d", "rs_percentile_60d"]].mean(axis=1, skipna=False)
    return out
