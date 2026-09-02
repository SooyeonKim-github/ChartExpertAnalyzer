from __future__ import annotations

import pandas as pd

from ..models import SignalScore


def _prior_max(series: pd.Series, n: int) -> float | None:
    if len(series) < n + 1:
        return None
    vals = pd.to_numeric(series.iloc[-(n + 1):-1], errors="coerce").dropna()
    return None if vals.empty else float(vals.max())


def score_daily_position(daily: pd.DataFrame) -> SignalScore:
    if daily is None or len(daily) < 21:
        return SignalScore(None, {"reason": "insufficient_daily_history"})

    cur = daily.iloc[-1]
    close = float(cur["close"])
    high = float(cur["high"])
    high10 = _prior_max(daily["high"], 10)
    high20 = _prior_max(daily["high"], 20)
    high52 = _prior_max(daily["high"], 52)
    close20 = _prior_max(daily["close"], 20)
    high60 = _prior_max(daily["high"], 60)

    b10 = high10 is not None and high > high10
    b20 = high20 is not None and high > high20
    b52 = high52 is not None and high > high52
    close20_high = close20 is not None and close >= close20
    previous_high_break = high60 is not None and close > high60

    score = 0.0
    score += 15.0 if b10 else 0.0
    score += 20.0 if b20 else 0.0
    score += 15.0 if b52 else 0.0
    score += 15.0 if close20_high else 0.0
    score += 25.0 if previous_high_break else 0.0

    distance_20d_high = None
    if high20 and high20 > 0:
        distance_20d_high = (close / high20 - 1.0) * 100.0
        if not b20 and distance_20d_high >= -2.0:
            score += 10.0

    return SignalScore(min(100.0, round(score, 2)), {
        "high_10d_break": bool(b10),
        "high_20d_break": bool(b20),
        "high_52d_break": bool(b52),
        "previous_high_break": bool(previous_high_break),
        "close_20d_high": bool(close20_high),
        "distance_20d_high": None if distance_20d_high is None else round(float(distance_20d_high), 3),
        "breakout_reference": high20,
    })


def score_ma_structure(daily: pd.DataFrame) -> SignalScore:
    if daily is None or len(daily) < 120:
        return SignalScore(None, {"reason": "insufficient_ma_history"})
    close = pd.to_numeric(daily["close"], errors="coerce")
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    ma120 = float(close.tail(120).mean())
    cur = float(close.iloc[-1])
    if ma20 > ma60 > ma120:
        score = 100.0
        state = "MA20>MA60>MA120"
    elif cur > ma20 and ma20 > ma60:
        score = 75.0
        state = "ABOVE_MA20_MA20>MA60"
    elif cur > ma20:
        score = 50.0
        state = "ABOVE_MA20"
    else:
        score = 0.0
        state = "WEAK"
    return SignalScore(score, {"state": state, "ma20": ma20, "ma60": ma60, "ma120": ma120})
