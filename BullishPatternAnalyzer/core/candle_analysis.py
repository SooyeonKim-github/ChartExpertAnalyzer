from __future__ import annotations

import math
import pandas as pd

from config import CANDLE, VOLUME_FILTER


def _shape(row: pd.Series) -> dict:
    o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
    rng = max(h - l, 1e-12)
    body = abs(c - o)
    upper = max(0.0, h - max(o, c))
    lower = max(0.0, min(o, c) - l)
    return {
        "bullish": c > o,
        "bearish": c < o,
        "body_ratio": body / rng,
        "upper_wick_ratio": upper / rng,
        "lower_wick_ratio": lower / rng,
        "close_location": (c - l) / rng,
    }


def _bullish_engulfing(prev: pd.Series, cur: pd.Series) -> tuple[bool, bool]:
    p, c = _shape(prev), _shape(cur)
    body_engulf = (
        p["bearish"] and c["bullish"]
        and float(cur["open"]) <= float(prev["close"])
        and float(cur["close"]) >= float(prev["open"])
    )
    full_range = body_engulf and float(cur["low"]) < float(prev["low"]) and float(cur["high"]) > float(prev["high"])
    return bool(body_engulf), bool(full_range)


def analyze_candles(df: pd.DataFrame, breakout_level: float | None = None) -> dict:
    if df is None or df.empty:
        return {"score": 0.0, "signal": "NONE", "bearish_warning": False}

    cur = df.iloc[-1]
    s = _shape(cur)
    vol_ma = float(cur.get("vol_ma20", float("nan")))
    vol_ratio = float(cur["volume"] / vol_ma) if math.isfinite(vol_ma) and vol_ma > 0 else 0.0

    momentum_bullish = bool(
        s["bullish"]
        and s["body_ratio"] >= CANDLE.momentum_body_ratio_min
        and s["close_location"] >= CANDLE.momentum_close_location_min
    )
    bullish_pin = bool(
        s["lower_wick_ratio"] >= CANDLE.pin_lower_wick_ratio_min
        and s["body_ratio"] <= CANDLE.pin_body_ratio_max
        and s["close_location"] >= 0.60
    )

    bullish_engulfing = False
    full_range_engulfing = False
    engulfing_confirmed = False
    if len(df) >= 2:
        bullish_engulfing, full_range_engulfing = _bullish_engulfing(df.iloc[-2], cur)
    if len(df) >= 3:
        prior_engulf, _ = _bullish_engulfing(df.iloc[-3], df.iloc[-2])
        engulfing_confirmed = bool(
            prior_engulf and s["bullish"] and float(cur["close"]) > float(df.iloc[-2]["close"])
        )

    inside_bar_breakout = False
    if len(df) >= 3:
        mother, inside = df.iloc[-3], df.iloc[-2]
        is_inside = float(inside["high"]) < float(mother["high"]) and float(inside["low"]) > float(mother["low"])
        inside_bar_breakout = bool(
            is_inside
            and float(cur["close"]) > float(mother["high"])
            and float(cur["volume"]) > float(mother["volume"])
        )

    morning_star = False
    morning_star_strong = False
    if len(df) >= 3:
        a, b, c = df.iloc[-3], df.iloc[-2], cur
        sa, sb, sc = _shape(a), _shape(b), s
        midpoint = (float(a["open"]) + float(a["close"])) / 2.0
        morning_star = bool(
            sa["bearish"] and sa["body_ratio"] >= 0.50
            and sb["body_ratio"] <= 0.35
            and sc["bullish"] and sc["body_ratio"] >= 0.50
            and float(c["close"]) > midpoint
        )
        morning_star_strong = bool(morning_star and float(c["close"]) > float(a["high"]))

    three_white_soldiers = False
    if len(df) >= 3:
        last3 = df.tail(3)
        shapes = [_shape(last3.iloc[i]) for i in range(3)]
        three_white_soldiers = bool(
            all(x["bullish"] for x in shapes)
            and all(x["body_ratio"] >= 0.45 for x in shapes)
            and float(last3.iloc[0]["close"]) < float(last3.iloc[1]["close"]) < float(last3.iloc[2]["close"])
        )

    recent_high = float(df["high"].tail(CANDLE.high_zone_lookback).max())
    near_high_zone = bool(recent_high > 0 and float(cur["close"]) >= recent_high * CANDLE.high_zone_ratio)
    long_upper_now = s["upper_wick_ratio"] >= CANDLE.long_upper_wick_ratio_min
    repeated_upper_wick_distribution = False
    if len(df) >= 2:
        prev_shape = _shape(df.iloc[-2])
        repeated_upper_wick_distribution = bool(
            near_high_zone
            and long_upper_now
            and prev_shape["upper_wick_ratio"] >= CANDLE.long_upper_wick_ratio_min
            and float(cur["volume"]) > float(df.iloc[-2]["volume"])
            and vol_ratio >= VOLUME_FILTER.distribution_min_ratio
        )

    resistance_near = bool(
        breakout_level and breakout_level > 0
        and abs(float(cur["close"]) / float(breakout_level) - 1.0) <= 0.03
    )
    narrow_high_volume_warning = bool(
        s["body_ratio"] <= CANDLE.narrow_body_ratio_max
        and vol_ratio >= VOLUME_FILTER.distribution_min_ratio
        and (near_high_zone or resistance_near)
    )
    bearish_warning = bool(repeated_upper_wick_distribution or narrow_high_volume_warning)

    labels: list[str] = []
    score = 10.0 if s["bullish"] else 0.0
    if momentum_bullish: score += 30; labels.append("MOMENTUM_BULLISH")
    if bullish_pin: score += 22; labels.append("BULLISH_PIN")
    if bullish_engulfing: score += 25; labels.append("BULLISH_ENGULFING")
    if full_range_engulfing: score += 10; labels.append("FULL_RANGE_ENGULFING")
    if engulfing_confirmed: score += 15; labels.append("ENGULFING_CONFIRMED")
    if inside_bar_breakout: score += 30; labels.append("INSIDE_BAR_BREAKOUT")
    if morning_star: score += 28; labels.append("MORNING_STAR")
    if morning_star_strong: score += 12; labels.append("MORNING_STAR_STRONG")
    if three_white_soldiers: score += 20; labels.append("THREE_WHITE_SOLDIERS")
    if s["close_location"] >= 0.80 and s["bullish"]: score += 8
    if repeated_upper_wick_distribution: score -= 45; labels.append("UPPER_WICK_DISTRIBUTION_WARNING")
    if narrow_high_volume_warning: score -= 30; labels.append("NARROW_HIGH_VOLUME_WARNING")

    return {
        "score": round(max(0.0, min(100.0, score)), 2),
        "signal": "|".join(labels) if labels else "NONE",
        "bullish_momentum_candle": momentum_bullish,
        "bullish_pin_bar": bullish_pin,
        "bullish_engulfing": bullish_engulfing,
        "full_range_engulfing": full_range_engulfing,
        "engulfing_confirmed": engulfing_confirmed,
        "inside_bar_breakout": inside_bar_breakout,
        "morning_star": morning_star,
        "morning_star_strong": morning_star_strong,
        "three_white_soldiers": three_white_soldiers,
        "body_ratio": round(s["body_ratio"], 5),
        "upper_wick_ratio": round(s["upper_wick_ratio"], 5),
        "lower_wick_ratio": round(s["lower_wick_ratio"], 5),
        "close_location": round(s["close_location"], 5),
        "near_high_zone": near_high_zone,
        "upper_wick_distribution_warning": repeated_upper_wick_distribution,
        "narrow_high_volume_warning": narrow_high_volume_warning,
        "bearish_warning": bearish_warning,
    }
