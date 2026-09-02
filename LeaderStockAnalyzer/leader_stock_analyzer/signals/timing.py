from __future__ import annotations

import pandas as pd

from ..models import TimingScore


def score_timing(daily: pd.DataFrame, intraday: pd.DataFrame | None, breakout_reference: float | None) -> TimingScore:
    if daily is None or len(daily) < 21 or breakout_reference is None or breakout_reference <= 0:
        return TimingScore(0.0, "DISCOVERED", "insufficient", {"reason": "breakout_reference_unavailable"})

    if intraday is not None and not intraday.empty and len(intraday) >= 8:
        df = intraday.copy()
        crossed = df["high"] >= breakout_reference
        if not crossed.any():
            return TimingScore(25.0, "DISCOVERED", "intraday", {"breakout": False})
        first_idx = crossed[crossed].index[0]
        after = df.loc[first_idx:]
        breakout = True
        pullback = bool(((after["low"] <= breakout_reference * 1.03) & (after["low"] >= breakout_reference * 0.97)).any())
        cur = float(df["close"].iloc[-1])
        support_hold = cur >= breakout_reference and float(after["low"].min()) >= breakout_reference * 0.97
        turn = len(df) >= 3 and float(df["close"].iloc[-1]) > float(df["close"].iloc[-2]) and float(df["low"].iloc[-1]) >= float(df["low"].iloc[-2])
        score = 35.0 + (25.0 if pullback else 0.0) + (20.0 if support_hold else 0.0) + (20.0 if turn else 0.0)
        if pullback and support_hold and turn:
            state = "ENTRY_READY"
        elif pullback and support_hold:
            state = "SUPPORT_TEST"
        elif pullback:
            state = "PULLBACK_WAIT"
        else:
            state = "BREAKOUT"
        return TimingScore(min(100.0, score), state, "intraday", {
            "breakout": breakout,
            "pullback": pullback,
            "support_hold": support_hold,
            "turn": turn,
            "breakout_reference": breakout_reference,
        })

    cur = daily.iloc[-1]
    close = float(cur["close"])
    high = float(cur["high"])
    low = float(cur["low"])
    volume = float(cur.get("volume", 0.0))
    prior_vol = float(pd.to_numeric(daily["volume"], errors="coerce").iloc[-21:-1].mean())
    volume_ratio = None if prior_vol <= 0 else volume / prior_vol
    breakout = high > breakout_reference
    close_above = close >= breakout_reference
    near_high = high > low and (close - low) / (high - low) >= 0.75
    volume_ok = volume_ratio is not None and volume_ratio >= 1.15
    score = (40.0 if breakout else 0.0) + (25.0 if close_above else 0.0) + (20.0 if near_high else 0.0) + (15.0 if volume_ok else 0.0)
    state = "DAILY_BREAKOUT_PROXY" if breakout else "DISCOVERED"
    return TimingScore(score, state, "daily_proxy", {
        "breakout": breakout,
        "close_above_breakout": close_above,
        "close_near_high": near_high,
        "volume_ratio_20": volume_ratio,
        "breakout_reference": breakout_reference,
        "note": "Minute bars unavailable: pullback/support/turn are not inferred.",
    })
