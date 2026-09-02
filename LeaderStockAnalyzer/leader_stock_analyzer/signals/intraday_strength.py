from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import SignalScore


def _window_return(close: pd.Series, bars: int) -> float | None:
    if len(close) <= bars:
        return None
    base = float(close.iloc[-bars - 1])
    if base <= 0:
        return None
    return (float(close.iloc[-1]) / base - 1.0) * 100.0


def score_intraday_strength(intraday: pd.DataFrame, cfg: dict) -> SignalScore:
    if intraday is None or intraday.empty or len(intraday) < 5:
        return SignalScore(None, {"reason": "intraday_unavailable"})

    df = intraday.copy()
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    value = pd.to_numeric(df.get("trading_value", close * volume), errors="coerce").fillna(0.0)

    prior_high = high.cummax().shift(1)
    high_break_count = int((high > prior_high).fillna(False).sum())
    day_high = float(high.max())
    day_low = float(low.min())
    cur = float(close.iloc[-1])
    close_location = 0.5 if day_high <= day_low else (cur - day_low) / (day_high - day_low)

    total_vol = float(volume.sum())
    vwap = None if total_vol <= 0 else float((close * volume).sum() / total_vol)
    above_vwap = vwap is not None and cur >= vwap

    r3 = _window_return(close, 3)
    r10 = _window_return(close, 10)
    v3 = float(value.tail(3).sum())
    v10 = float(value.tail(10).sum())
    burst = r3 is not None and r3 >= 3.5 and v3 >= cfg["money_flow"]["intraday_3m_min"]

    score = min(45.0, high_break_count * 7.5)
    score += float(np.clip(close_location, 0.0, 1.0)) * 25.0
    score += 15.0 if above_vwap else 0.0
    score += 15.0 if burst else 0.0

    return SignalScore(min(100.0, round(score, 2)), {
        "high_break_count": high_break_count,
        "close_location": round(float(close_location), 4),
        "vwap": vwap,
        "above_vwap": bool(above_vwap),
        "return_3m": None if r3 is None else round(r3, 3),
        "return_10m": None if r10 is None else round(r10, 3),
        "trading_value_3m": v3,
        "trading_value_10m": v10,
        "momentum_burst": bool(burst),
    })
