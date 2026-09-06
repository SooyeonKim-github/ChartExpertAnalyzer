from __future__ import annotations

import pandas as pd


def add_moving_average_indicators(
    df: pd.DataFrame,
    *,
    ma_short: int = 50,
    ma_long: int = 150,
    slope_lookback: int = 20,
) -> pd.DataFrame:
    """Add MA50/MA150 and MA150 slope without look-ahead.

    MA150 is used as the daily-bar proxy for the lecture's 30-week moving average.
    Slope is the percentage change of MA150 over `slope_lookback` trading bars.
    """
    if "close" not in df.columns:
        raise ValueError("OHLCV frame must contain 'close'")
    if ma_short <= 0 or ma_long <= 0 or slope_lookback <= 0:
        raise ValueError("Moving-average periods and slope_lookback must be positive")
    if ma_short >= ma_long:
        raise ValueError("ma_short must be smaller than ma_long")

    out = df.copy()
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["ma50"] = out["close"].rolling(ma_short, min_periods=ma_short).mean()
    out["ma150"] = out["close"].rolling(ma_long, min_periods=ma_long).mean()
    out["ma150_slope_pct"] = (
        out["ma150"] / out["ma150"].shift(slope_lookback) - 1.0
    ) * 100.0
    out["close_vs_ma150_pct"] = (out["close"] / out["ma150"] - 1.0) * 100.0
    out["ma50_vs_ma150_pct"] = (out["ma50"] / out["ma150"] - 1.0) * 100.0
    return out
