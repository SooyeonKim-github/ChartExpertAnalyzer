from __future__ import annotations

import pandas as pd

from config import StrategyConfig
from core.models import Pivot


def analyze_market_structure(df: pd.DataFrame, highs: list[Pivot], lows: list[Pivot], cfg: StrategyConfig) -> dict:
    n = len(df)
    floor = max(0, n - cfg.structure_lookback_bars)
    hs = [p for p in highs if p.pos >= floor]
    ls = [p for p in lows if p.pos >= floor]
    out = {
        "valid": False, "higher_high": False, "higher_low": False, "uptrend": False,
        "pullback": False, "prior_low_held": False, "pullback_pct": float("nan"),
        "last_high": None, "prev_high": None, "last_low": None, "prev_low": None,
    }
    if len(hs) < 2 or len(ls) < 2:
        return out
    prev_h, last_h = hs[-2], hs[-1]
    prev_l, last_l = ls[-2], ls[-1]
    higher_high = last_h.price > prev_h.price
    higher_low = last_l.price > prev_l.price
    uptrend = higher_high and higher_low

    lookback = df.iloc[max(0, n-cfg.pullback_lookback_bars):]
    recent_peak = float(lookback["High"].max())
    close = float(df["Close"].iloc[-1])
    pullback_pct = (recent_peak - close) / recent_peak if recent_peak > 0 else 0.0
    pullback = cfg.min_pullback_pct <= pullback_pct <= cfg.max_pullback_pct
    prior_low_held = float(df["Low"].iloc[-1]) >= last_l.price * (1.0 - cfg.prior_low_break_tolerance)

    out.update({
        "valid": True, "higher_high": higher_high, "higher_low": higher_low, "uptrend": uptrend,
        "pullback": pullback, "prior_low_held": prior_low_held, "pullback_pct": pullback_pct,
        "last_high": last_h, "prev_high": prev_h, "last_low": last_l, "prev_low": prev_l,
    })
    return out
