from __future__ import annotations

import math
import pandas as pd

from config import PullbackConfig
from models import ImpulseContext, PullbackContext, SupportContext


def _finite(v) -> bool:
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


def detect_support(d: pd.DataFrame, impulse: ImpulseContext, pullback: PullbackContext, cfg: PullbackConfig) -> SupportContext:
    if d.empty:
        return SupportContext()

    close = float(d["Close"].iloc[-1])
    levels: dict[str, float] = {}
    for p in cfg.ma_periods:
        v = d[f"MA{p}"].iloc[-1]
        if _finite(v):
            levels[f"MA{p}"] = float(v)

    if impulse.available:
        if _finite(impulse.breakout_level):
            levels["BREAKOUT_LEVEL"] = float(impulse.breakout_level)
        if _finite(impulse.open_price):
            levels["IMPULSE_OPEN"] = float(impulse.open_price)
        if _finite(impulse.base_price) and _finite(impulse.high_price):
            levels["IMPULSE_MID"] = float((impulse.base_price + impulse.high_price) / 2.0)

    if not levels or close <= 0:
        return SupportContext(levels=levels)

    eligible = {
        name: level for name, level in levels.items()
        if level > 0 and level <= close * (1 + cfg.reclaim_tolerance_pct / 100.0)
    }
    if not eligible:
        eligible = {name: level for name, level in levels.items() if level > 0}
    distances = {name: abs(close / level - 1.0) * 100.0 for name, level in eligible.items()}
    nearest_name = min(distances, key=distances.get)
    nearest_level = eligible[nearest_name]
    nearest_dist = distances[nearest_name]

    confluence = sum(1 for x in distances.values() if x <= cfg.support_near_pct)
    near_ma = any(name.startswith("MA") and dist <= cfg.support_near_pct for name, dist in distances.items())
    near_price = any(not name.startswith("MA") and dist <= cfg.support_near_pct for name, dist in distances.items())

    recent = d.tail(cfg.support_touch_lookback_bars)
    tolerance = cfg.support_touch_tolerance_pct / 100.0
    touch_count = int(
        ((recent["Low"] <= nearest_level * (1 + tolerance)) & (recent["High"] >= nearest_level * (1 - tolerance))).sum()
    )

    bb_lower = float(d["BB_Lower"].iloc[-1]) if pd.notna(d["BB_Lower"].iloc[-1]) else float("nan")
    bb_mid = float(d["BB_Mid"].iloc[-1]) if pd.notna(d["BB_Mid"].iloc[-1]) else float("nan")
    bb_lower_prev = float(d["BB_Lower"].iloc[-6]) if len(d) >= 6 and pd.notna(d["BB_Lower"].iloc[-6]) else float("nan")
    bb_rising = _finite(bb_lower) and _finite(bb_lower_prev) and bb_lower > bb_lower_prev
    bb_support = bool(
        bb_rising
        and ((_finite(bb_lower) and abs(close / bb_lower - 1.0) * 100 <= cfg.support_max_pct)
             or (_finite(bb_mid) and abs(close / bb_mid - 1.0) * 100 <= cfg.support_near_pct))
    )

    support_held = bool(
        pullback.available
        and pullback.low_price >= nearest_level * (1 - cfg.support_break_pct / 100.0)
        and close >= nearest_level * (1 - cfg.reclaim_tolerance_pct / 100.0)
    )

    return SupportContext(
        nearest_name=nearest_name, nearest_level=nearest_level, distance_pct=nearest_dist,
        confluence_count=confluence, touch_count=touch_count, near_ma=near_ma,
        near_price_level=near_price, bb_support=bb_support, support_held=support_held, levels=levels,
    )
