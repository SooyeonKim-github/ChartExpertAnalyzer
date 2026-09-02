from __future__ import annotations

import pandas as pd


def stage2_limit_price(stage1_price: float, pullback_pct: float) -> float:
    return stage1_price * (1.0 - pullback_pct)


def stage2_touched(bar: pd.Series, limit_price: float) -> bool:
    return float(bar["Low"]) <= limit_price


def stage2_fill_price(bar: pd.Series, limit_price: float) -> float:
    # Buy limit: if the market gaps below the limit, assume the open is obtained.
    return min(float(bar["Open"]), limit_price)


def stage3_rebound_confirmed(current: pd.Series, previous: pd.Series) -> bool:
    required = ("Open", "Close", "High", "MA5")
    if any(pd.isna(current.get(col)) for col in required):
        return False
    if pd.isna(previous.get("High")):
        return False
    return (
        float(current["Close"]) > float(current["Open"])
        and float(current["Close"]) > float(previous["High"])
        and float(current["Close"]) > float(current["MA5"])
    )
