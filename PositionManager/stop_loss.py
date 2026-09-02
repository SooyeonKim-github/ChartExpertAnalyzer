from __future__ import annotations

import pandas as pd


def initial_stop_price(
    history: pd.DataFrame,
    stage1_price: float,
    lookback_bars: int,
    structural_buffer_pct: float,
    max_stop_pct: float,
) -> float:
    hard_floor = stage1_price * (1.0 - max_stop_pct)
    if history.empty or "Low" not in history.columns:
        return hard_floor

    recent = history.tail(max(1, lookback_bars))
    low = pd.to_numeric(recent["Low"], errors="coerce").dropna()
    if low.empty:
        return hard_floor

    structural = float(low.min()) * (1.0 - structural_buffer_pct)
    stop = max(structural, hard_floor)
    if stop >= stage1_price:
        stop = hard_floor
    return stop


def stop_fill_price(bar: pd.Series, stop_price: float) -> float | None:
    open_price = float(bar["Open"])
    low_price = float(bar["Low"])
    if open_price <= stop_price:
        return open_price
    if low_price <= stop_price:
        return stop_price
    return None
