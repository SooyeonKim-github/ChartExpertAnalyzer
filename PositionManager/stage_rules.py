from __future__ import annotations

import pandas as pd


def bullish_rebound_confirmed(current: pd.Series, previous: pd.Series) -> bool:
    """Confirmation used for every V3 add-on buy.

    The add is approved only after a bullish close that breaks the previous high
    and finishes above MA5. The actual buy happens on the next trading-day open.
    """
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


def stage2_rebound_confirmed(current: pd.Series, previous: pd.Series) -> bool:
    return bullish_rebound_confirmed(current, previous)


def stage3_rebound_confirmed(current: pd.Series, previous: pd.Series) -> bool:
    return bullish_rebound_confirmed(current, previous)
