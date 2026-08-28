from __future__ import annotations

import numpy as np
import pandas as pd

from config import CONFIRMATION, MARKET, VOLUME_FILTER
from core.models import MarketRegime, RiskLevel


def _recent_breakout_context(df: pd.DataFrame, level: float | None) -> dict:
    if level is None or level <= 0 or df.empty or len(df) < 2:
        return {
            "found": False,
            "confirmed": False,
            "breakout_pos": None,
            "age_bars": None,
            "volume_ratio": 0.0,
            "current_breakout": False,
            "held": False,
        }

    threshold = float(level) * (1 + CONFIRMATION.breakout_min_pct)
    lookback = max(1, int(CONFIRMATION.breakout_lookback_bars))
    search_start = max(1, len(df) - lookback)
    breakout_pos = None

    for pos in range(search_start, len(df)):
        prev_close = float(df.iloc[pos - 1]["close"])
        close = float(df.iloc[pos]["close"])
        if prev_close < threshold <= close:
            breakout_pos = pos

    if breakout_pos is None:
        return {
            "found": False,
            "confirmed": False,
            "breakout_pos": None,
            "age_bars": None,
            "volume_ratio": 0.0,
            "current_breakout": False,
            "held": False,
        }

    breakout_row = df.iloc[breakout_pos]
    vol_ma = float(breakout_row.get("vol_ma20", np.nan))
    volume_ratio = (
        float(breakout_row["volume"] / vol_ma)
        if np.isfinite(vol_ma) and vol_ma > 0
        else 0.0
    )
    age_bars = len(df) - 1 - breakout_pos
    current_close = float(df.iloc[-1]["close"])
    held = current_close >= float(level) * (1 - CONFIRMATION.retest_tolerance_pct)

    return {
        "found": True,
        "confirmed": bool(held),
        "breakout_pos": breakout_pos,
        "age_bars": age_bars,
        "volume_ratio": volume_ratio,
        "current_breakout": age_bars == 0,
        "held": bool(held),
    }


def breakout_analysis(df: pd.DataFrame, level: float | None) -> dict:
    if level is None or level <= 0 or df.empty:
        return {
            "confirmed": False,
            "score": 0.0,
            "volume_ratio": 0.0,
            "distance_pct": None,
            "breakout_age_bars": None,
            "current_breakout": False,
            "held": False,
        }

    close = float(df.iloc[-1]["close"])
    distance = close / level - 1.0
    context = _recent_breakout_context(df, level)
    volume_ratio = float(context["volume_ratio"])
    volume_score = min(
        100.0,
        max(
            0.0,
            volume_ratio / CONFIRMATION.breakout_volume_ratio_strong * 100.0,
        ),
    )
    score = 0.65 * (100.0 if context["confirmed"] else 0.0) + 0.35 * volume_score
    return {
        "confirmed": bool(context["confirmed"]),
        "score": round(score, 2),
        "volume_ratio": round(volume_ratio, 3),
        "distance_pct": round(distance, 5),
        "breakout_age_bars": context["age_bars"],
        "current_breakout": bool(context["current_breakout"]),
        "held": bool(context["held"]),
    }


def volume_quality(df: pd.DataFrame, breakout_level: float | None = None) -> dict:
    if df.empty:
        return {"score": 0.0, "ratio": 0.0, "filter_pass": False}

    context = _recent_breakout_context(df, breakout_level)
    signal_pos = context["breakout_pos"] if context["found"] else len(df) - 1
    row = df.iloc[signal_pos]
    ma = float(row.get("vol_ma20", np.nan))
    ratio = float(row["volume"] / ma) if np.isfinite(ma) and ma > 0 else 0.0
    oscillator = float(row.get("volume_oscillator_pct", np.nan))
    prev_oscillator = (
        float(df.iloc[signal_pos - 1].get("volume_oscillator_pct", np.nan))
        if signal_pos >= 1
        else np.nan
    )
    oscillator_positive = bool(np.isfinite(oscillator) and oscillator > 0)
    oscillator_rising = bool(
        np.isfinite(oscillator)
        and np.isfinite(prev_oscillator)
        and oscillator > prev_oscillator
    )

    prior = df.iloc[:signal_pos]
    short_mean = (
        float(prior["volume"].tail(VOLUME_FILTER.contraction_window).mean())
        if len(prior)
        else np.nan
    )
    ref_mean = (
        float(prior["volume"].tail(VOLUME_FILTER.reference_window).mean())
        if len(prior)
        else np.nan
    )
    contraction_ratio = (
        short_mean / ref_mean if np.isfinite(ref_mean) and ref_mean > 0 else np.nan
    )
    pre_breakout_contraction = bool(
        np.isfinite(contraction_ratio)
        and contraction_ratio <= VOLUME_FILTER.contraction_max_ratio
    )

    ratio_pass = ratio >= VOLUME_FILTER.breakout_min_ratio
    oscillator_pass = oscillator_positive if VOLUME_FILTER.require_positive_oscillator else True
    filter_pass = bool(
        (not VOLUME_FILTER.enabled)
        or (context["confirmed"] and ratio_pass and oscillator_pass)
    )

    score = 55.0 * min(1.0, ratio / max(VOLUME_FILTER.breakout_strong_ratio, 1e-9))
    if pre_breakout_contraction:
        score += 20.0
    if oscillator_positive:
        score += 15.0
    if oscillator_rising:
        score += 10.0
    if breakout_level and not context["confirmed"]:
        score *= 0.70

    price10 = (
        float(df["close"].iloc[-1] / df["close"].iloc[-10] - 1.0)
        if len(df) >= 10
        else np.nan
    )
    vol_slope = (
        float(
            np.polyfit(
                np.arange(min(10, len(df))),
                df["volume"].tail(10).to_numpy(float),
                1,
            )[0]
        )
        if len(df) >= 3
        else np.nan
    )
    bearish_volume_divergence = bool(
        np.isfinite(price10)
        and price10 > 0.03
        and np.isfinite(vol_slope)
        and vol_slope < 0
    )

    return {
        "score": round(max(0.0, min(100.0, score)), 2),
        "ratio": round(ratio, 3),
        "filter_pass": filter_pass,
        "pre_breakout_contraction": pre_breakout_contraction,
        "contraction_ratio": (
            None
            if not np.isfinite(contraction_ratio)
            else round(float(contraction_ratio), 4)
        ),
        "volume_oscillator_pct": (
            None if not np.isfinite(oscillator) else round(float(oscillator), 3)
        ),
        "volume_oscillator_positive": oscillator_positive,
        "volume_oscillator_rising": oscillator_rising,
        "bearish_volume_divergence": bearish_volume_divergence,
        "breakout_age_bars": context["age_bars"],
        "breakout_candle_used": bool(context["found"]),
    }


def indicator_bullish_divergence(df: pd.DataFrame, low_positions: list[int], column: str, min_delta: float = 2.0) -> bool:
    if len(low_positions) < 2 or column not in df:
        return False
    a, b = low_positions[-2], low_positions[-1]
    p1, p2 = float(df.iloc[a]["low"]), float(df.iloc[b]["low"])
    i1, i2 = float(df.iloc[a][column]), float(df.iloc[b][column])
    return bool(np.isfinite(i1) and np.isfinite(i2) and p2 <= p1 * 1.02 and i2 > i1 + min_delta)


def bullish_divergence(df: pd.DataFrame, low_positions: list[int]) -> bool:
    return indicator_bullish_divergence(df, low_positions, "rsi14", 2.0)


def momentum_quality(df: pd.DataFrame, divergence: bool = False, mfi_divergence: bool = False) -> dict:
    row = df.iloc[-1]
    close = float(row["close"])
    ma5 = float(row.get("ma5", np.nan))
    ma20 = float(row.get("ma20", np.nan))
    ma200 = float(row.get("ma200", np.nan))
    rsi = float(row.get("rsi14", np.nan))
    mfi = float(row.get("mfi14", np.nan))
    score = 0.0
    if np.isfinite(ma5) and close > ma5: score += 20
    if np.isfinite(ma20) and close > ma20: score += 20
    if np.isfinite(ma5) and np.isfinite(ma20) and ma5 > ma20: score += 15
    if np.isfinite(rsi) and 45 <= rsi <= 75: score += 15
    if np.isfinite(mfi) and 20 <= mfi <= 80: score += 10
    if np.isfinite(ma200) and close > ma200: score += 5
    if divergence: score += 8
    if mfi_divergence: score += 7
    return {
        "score": min(100.0, score),
        "rsi14": None if not np.isfinite(rsi) else round(rsi, 2),
        "mfi14": None if not np.isfinite(mfi) else round(mfi, 2),
        "above_ma200": bool(np.isfinite(ma200) and close > ma200),
    }


def ma_context(df: pd.DataFrame, reference_pos: int | None = None) -> dict:
    pos = len(df) - 1 if reference_pos is None else reference_pos
    row = df.iloc[pos]
    close = float(row["close"])
    ma20 = float(row.get("ma20", np.nan))
    dist = close / ma20 - 1.0 if np.isfinite(ma20) and ma20 else np.nan
    current = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else current
    ma5_reclaim = bool(np.isfinite(current.get("ma5", np.nan)) and np.isfinite(prev.get("ma5", np.nan)) and float(prev["close"]) <= float(prev["ma5"]) and float(current["close"]) > float(current["ma5"]))
    ma20_reclaim = bool(np.isfinite(current.get("ma20", np.nan)) and np.isfinite(prev.get("ma20", np.nan)) and float(prev["close"]) <= float(prev["ma20"]) and float(current["close"]) > float(current["ma20"]))
    return {"ma20_distance_pct": None if not np.isfinite(dist) else round(float(dist), 5), "above_ma20": bool(np.isfinite(ma20) and close >= ma20), "ma5_reclaim": ma5_reclaim, "ma20_reclaim": ma20_reclaim}


def retest_analysis(df: pd.DataFrame, level: float | None, breakout_confirmed: bool) -> dict:
    if not breakout_confirmed or not level or len(df) < 3:
        return {"valid": False, "score": 0.0}

    context = _recent_breakout_context(df, level)
    breakout_pos = context["breakout_pos"]
    if breakout_pos is None or breakout_pos >= len(df) - 1:
        return {"valid": False, "score": 35.0}

    start = max(breakout_pos + 1, len(df) - CONFIRMATION.retest_lookback_bars)
    recent = df.iloc[start:]
    if recent.empty:
        return {"valid": False, "score": 35.0}

    t = CONFIRMATION.retest_tolerance_pct
    touched = (
        (recent["low"] <= level * (1 + t))
        & (recent["low"] >= level * (1 - t))
    ).any()
    held = float(df.iloc[-1]["close"]) >= level * (1 - t)
    valid = bool(touched and held)
    return {"valid": valid, "score": 100.0 if valid else 35.0}


def risk_analysis(df: pd.DataFrame, breakout_level: float | None, stop_level: float | None) -> dict:
    row = df.iloc[-1]
    close = float(row["close"])
    atr = float(row.get("atr14", np.nan))
    chase_atr = max(0.0, (close - breakout_level) / atr) if breakout_level and np.isfinite(atr) and atr > 0 else None
    chase = RiskLevel.UNKNOWN if chase_atr is None else (RiskLevel.HIGH if chase_atr >= CONFIRMATION.chase_high_atr else RiskLevel.MEDIUM if chase_atr >= CONFIRMATION.chase_medium_atr else RiskLevel.LOW)
    stop_pct = max(0.0, (close - stop_level) / close) if stop_level and stop_level > 0 else None
    entry = RiskLevel.UNKNOWN if stop_pct is None else (RiskLevel.HIGH if stop_pct >= CONFIRMATION.entry_risk_high_pct else RiskLevel.MEDIUM if stop_pct >= CONFIRMATION.entry_risk_medium_pct else RiskLevel.LOW)
    return {"chase": chase, "entry": entry, "chase_atr": chase_atr, "stop_distance_pct": stop_pct}


def market_context(index_df: pd.DataFrame | None) -> MarketRegime:
    if index_df is None or len(index_df) < 60:
        return MarketRegime.UNKNOWN
    d = index_df.copy()
    d["ma20"] = d["close"].rolling(20).mean()
    d["ma60"] = d["close"].rolling(60).mean()
    row = d.iloc[-1]
    close, ma20, ma60 = float(row["close"]), float(row["ma20"]), float(row["ma60"])
    recent_high = float(d["close"].tail(max(60, MARKET.recent_window_bars)).max())
    drawdown = close / recent_high - 1.0 if recent_high > 0 else 0.0
    ma20_slope = float(d["ma20"].iloc[-1] - d["ma20"].iloc[-6])
    if drawdown <= MARKET.crash_drawdown_pct and close < ma20: return MarketRegime.CRASH
    if drawdown <= MARKET.weak_drawdown_pct or (close < ma20 and close < ma60): return MarketRegime.WEAK
    if close > ma20 > ma60 and ma20_slope > 0: return MarketRegime.BULLISH
    return MarketRegime.NEUTRAL
