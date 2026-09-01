from __future__ import annotations

import math
import numpy as np
import pandas as pd

from config import PullbackConfig
from models import PullbackContext, SupportContext


def build_risk_plan(d: pd.DataFrame, pullback: PullbackContext, support: SupportContext, cfg: PullbackConfig) -> dict:
    close = float(d["Close"].iloc[-1])
    candidates = []
    if pullback.available and math.isfinite(pullback.low_price):
        candidates.append(float(pullback.low_price))
    if math.isfinite(support.nearest_level):
        candidates.append(float(support.nearest_level) * 0.99)
    recent_low = float(d["Low"].tail(5).min())
    candidates.append(recent_low)
    stop = max(0.0, min(candidates)) if candidates else np.nan
    stop_distance = (close / stop - 1.0) * 100.0 if stop and stop > 0 else np.nan

    ma20 = float(d["MA20"].iloc[-1]) if pd.notna(d["MA20"].iloc[-1]) else np.nan
    ma20_ext = (close / ma20 - 1.0) * 100.0 if np.isfinite(ma20) and ma20 > 0 else np.nan
    chase_risk = bool(
        (np.isfinite(ma20_ext) and ma20_ext > cfg.max_ma20_extension_pct)
        or (np.isfinite(stop_distance) and stop_distance > cfg.max_stop_distance_pct)
    )
    return {
        "stop_price": stop,
        "stop_distance_pct": stop_distance,
        "ma20_extension_pct": ma20_ext,
        "chase_risk": chase_risk,
    }
