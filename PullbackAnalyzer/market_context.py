from __future__ import annotations

import numpy as np
import pandas as pd

from models import MarketContext


def _ret(series: pd.Series, bars: int) -> float:
    s = series.dropna()
    if len(s) <= bars:
        return np.nan
    return float(s.iloc[-1] / s.iloc[-bars - 1] - 1.0)


def analyze_market_context(stock_df: pd.DataFrame, market_df: pd.DataFrame | None) -> MarketContext:
    if market_df is None or market_df.empty:
        return MarketContext()

    m = market_df.copy().sort_index()
    m["MA20"] = m["Close"].rolling(20).mean()
    m["MA60"] = m["Close"].rolling(60).mean()
    market_ret20 = _ret(m["Close"], 20)
    market_ret60 = _ret(m["Close"], 60)
    above60 = bool(pd.notna(m["MA60"].iloc[-1]) and float(m["Close"].iloc[-1]) > float(m["MA60"].iloc[-1]))
    ma60_up = bool(len(m) > 10 and pd.notna(m["MA60"].iloc[-10]) and float(m["MA60"].iloc[-1]) > float(m["MA60"].iloc[-10]))
    if above60 and ma60_up:
        regime = "uptrend"
    elif not above60 and not ma60_up:
        regime = "downtrend"
    else:
        regime = "range"

    s = stock_df[["Close"]].rename(columns={"Close": "stock"}).copy()
    mm = market_df[["Close"]].rename(columns={"Close": "market"}).copy()
    s.index = pd.to_datetime(s.index).normalize()
    mm.index = pd.to_datetime(mm.index).normalize()
    x = s.join(mm, how="inner").dropna().sort_index()
    rs20 = rs60 = down_hit = np.nan
    if len(x) >= 22:
        rs20 = _ret(x["stock"], 20) - _ret(x["market"], 20)
        if len(x) >= 61:
            rs60 = _ret(x["stock"], 60) - _ret(x["market"], 60)
        daily = x.pct_change().dropna().tail(20)
        down = daily[daily["market"] < 0]
        if len(down) >= 3:
            down_hit = float((down["stock"] > down["market"]).mean())

    score = 50.0
    if np.isfinite(rs20):
        score += float(np.clip(rs20 / 0.10 * 20.0, -20.0, 20.0))
    if np.isfinite(rs60):
        score += float(np.clip(rs60 / 0.20 * 15.0, -15.0, 15.0))
    if np.isfinite(down_hit):
        score += float(np.clip((down_hit - 0.5) * 20.0, -10.0, 10.0))
    score = float(np.clip(score, 0.0, 100.0))

    return MarketContext(
        available=True, regime=regime, market_ret20=market_ret20, market_ret60=market_ret60,
        market_above_ma60=above60, rs20=rs20, rs60=rs60,
        down_day_hit_rate20=down_hit, rs_score=round(score, 2),
    )
