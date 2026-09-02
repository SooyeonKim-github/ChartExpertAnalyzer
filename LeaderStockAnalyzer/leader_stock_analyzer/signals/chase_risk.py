from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import SignalScore


def score_chase_risk(daily: pd.DataFrame, return_pct: float) -> SignalScore:
    if daily is None or len(daily) < 6:
        return SignalScore(50.0, {"reason": "insufficient_history_default"})
    cur = daily.iloc[-1]
    close = float(cur["close"])
    open_ = float(cur["open"])
    high = float(cur["high"])
    low = float(cur["low"])
    volume = float(cur.get("volume", 0.0))

    ma5 = float(pd.to_numeric(daily["close"], errors="coerce").tail(5).mean())
    distance_ma5 = 0.0 if ma5 <= 0 else (close / ma5 - 1.0) * 100.0
    candle_range = max(high - low, 1e-9)
    upper_wick_ratio = max(0.0, (high - max(close, open_)) / candle_range)

    prev_returns = pd.to_numeric(daily["close"], errors="coerce").pct_change().tail(6).iloc[:-1] * 100.0
    recent_surge_count = int((prev_returns >= 7.0).sum())
    base_vol = float(pd.to_numeric(daily["volume"], errors="coerce").iloc[-21:-1].mean()) if len(daily) >= 21 else 0.0
    volume_ratio = None if base_vol <= 0 else volume / base_vol

    risk = 0.0
    if return_pct >= 20:
        risk += 20.0
    elif return_pct >= 15:
        risk += 14.0
    elif return_pct >= 10:
        risk += 8.0
    if distance_ma5 >= 12:
        risk += 20.0
    elif distance_ma5 >= 8:
        risk += 12.0
    if upper_wick_ratio >= 0.4:
        risk += 25.0
    elif upper_wick_ratio >= 0.25:
        risk += 12.0
    risk += min(20.0, recent_surge_count * 7.0)
    if volume_ratio is not None and volume_ratio >= 4.0 and upper_wick_ratio >= 0.2:
        risk += 15.0

    return SignalScore(round(float(np.clip(risk, 0.0, 100.0)), 2), {
        "distance_ma5_pct": round(distance_ma5, 3),
        "upper_wick_ratio": round(upper_wick_ratio, 4),
        "recent_surge_count": recent_surge_count,
        "volume_ratio_20": None if volume_ratio is None else round(volume_ratio, 3),
    })
