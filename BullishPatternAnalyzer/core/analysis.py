from __future__ import annotations

import numpy as np
import pandas as pd

from config import CONFIRMATION, MARKET
from core.models import MarketRegime, RiskLevel


def breakout_analysis(df: pd.DataFrame, level: float | None) -> dict:
    if level is None or level <= 0 or df.empty:
        return {"confirmed": False, "score": 0.0, "volume_ratio": 0.0, "distance_pct": None}
    row = df.iloc[-1]
    close = float(row["close"])
    vol_ma = float(row.get("vol_ma20", np.nan))
    volume_ratio = float(row["volume"] / vol_ma) if np.isfinite(vol_ma) and vol_ma > 0 else 0.0
    distance = close / level - 1.0
    close_ok = close >= level * (1 + CONFIRMATION.breakout_min_pct)
    volume_score = min(100.0, max(0.0, volume_ratio / CONFIRMATION.breakout_volume_ratio_strong * 100.0))
    score = 0.65 * (100.0 if close_ok else 0.0) + 0.35 * volume_score
    return {"confirmed": bool(close_ok), "score": round(score, 2), "volume_ratio": round(volume_ratio, 3), "distance_pct": round(distance, 5)}


def volume_quality(df: pd.DataFrame, breakout_level: float | None = None) -> dict:
    if df.empty: return {"score": 0.0, "ratio": 0.0}
    row = df.iloc[-1]
    ma = float(row.get("vol_ma20", np.nan))
    ratio = float(row["volume"] / ma) if np.isfinite(ma) and ma > 0 else 0.0
    score = min(100.0, ratio / CONFIRMATION.breakout_volume_ratio_strong * 100.0)
    if breakout_level and float(row["close"]) <= breakout_level: score *= 0.75
    return {"score": round(score, 2), "ratio": round(ratio, 3)}


def bullish_divergence(df: pd.DataFrame, low_positions: list[int]) -> bool:
    if len(low_positions) < 2 or "rsi14" not in df: return False
    a, b = low_positions[-2], low_positions[-1]
    p1, p2 = float(df.iloc[a]["low"]), float(df.iloc[b]["low"])
    r1, r2 = float(df.iloc[a]["rsi14"]), float(df.iloc[b]["rsi14"])
    return bool(np.isfinite(r1) and np.isfinite(r2) and p2 <= p1 * 1.02 and r2 > r1 + 2.0)


def momentum_quality(df: pd.DataFrame, divergence: bool = False) -> dict:
    row = df.iloc[-1]
    close = float(row["close"]); ma5 = float(row.get("ma5", np.nan)); ma20 = float(row.get("ma20", np.nan)); rsi = float(row.get("rsi14", np.nan))
    score = 0.0
    if np.isfinite(ma5) and close > ma5: score += 25
    if np.isfinite(ma20) and close > ma20: score += 25
    if np.isfinite(ma5) and np.isfinite(ma20) and ma5 > ma20: score += 20
    if np.isfinite(rsi) and 45 <= rsi <= 75: score += 20
    if divergence: score += 10
    return {"score": min(100.0, score), "rsi14": None if not np.isfinite(rsi) else round(rsi, 2)}


def ma_context(df: pd.DataFrame, reference_pos: int | None = None) -> dict:
    pos = len(df) - 1 if reference_pos is None else reference_pos
    row = df.iloc[pos]; close = float(row["close"]); ma20 = float(row.get("ma20", np.nan))
    dist = close / ma20 - 1.0 if np.isfinite(ma20) and ma20 else np.nan
    current = df.iloc[-1]; prev = df.iloc[-2] if len(df) >= 2 else current
    ma5_reclaim = bool(np.isfinite(current.get("ma5", np.nan)) and np.isfinite(prev.get("ma5", np.nan)) and float(prev["close"]) <= float(prev["ma5"]) and float(current["close"]) > float(current["ma5"]))
    ma20_reclaim = bool(np.isfinite(current.get("ma20", np.nan)) and np.isfinite(prev.get("ma20", np.nan)) and float(prev["close"]) <= float(prev["ma20"]) and float(current["close"]) > float(current["ma20"]))
    return {"ma20_distance_pct": None if not np.isfinite(dist) else round(float(dist), 5), "above_ma20": bool(np.isfinite(ma20) and close >= ma20), "ma5_reclaim": ma5_reclaim, "ma20_reclaim": ma20_reclaim}


def retest_analysis(df: pd.DataFrame, level: float | None, breakout_confirmed: bool) -> dict:
    if not breakout_confirmed or not level or len(df) < 3: return {"valid": False, "score": 0.0}
    recent = df.tail(CONFIRMATION.retest_lookback_bars); t = CONFIRMATION.retest_tolerance_pct
    touched = ((recent["low"] <= level * (1 + t)) & (recent["low"] >= level * (1 - t))).any(); held = float(df.iloc[-1]["close"]) >= level
    valid = bool(touched and held)
    return {"valid": valid, "score": 100.0 if valid else 35.0}


def risk_analysis(df: pd.DataFrame, breakout_level: float | None, stop_level: float | None) -> dict:
    row = df.iloc[-1]; close = float(row["close"]); atr = float(row.get("atr14", np.nan))
    chase_atr = max(0.0, (close - breakout_level) / atr) if breakout_level and np.isfinite(atr) and atr > 0 else None
    chase = RiskLevel.UNKNOWN if chase_atr is None else (RiskLevel.HIGH if chase_atr >= CONFIRMATION.chase_high_atr else RiskLevel.MEDIUM if chase_atr >= CONFIRMATION.chase_medium_atr else RiskLevel.LOW)
    stop_pct = max(0.0, (close - stop_level) / close) if stop_level and stop_level > 0 else None
    entry = RiskLevel.UNKNOWN if stop_pct is None else (RiskLevel.HIGH if stop_pct >= CONFIRMATION.entry_risk_high_pct else RiskLevel.MEDIUM if stop_pct >= CONFIRMATION.entry_risk_medium_pct else RiskLevel.LOW)
    return {"chase": chase, "entry": entry, "chase_atr": chase_atr, "stop_distance_pct": stop_pct}


def market_context(index_df: pd.DataFrame | None) -> MarketRegime:
    if index_df is None or len(index_df) < 60: return MarketRegime.UNKNOWN
    d = index_df.copy(); d["ma20"] = d["close"].rolling(20).mean(); d["ma60"] = d["close"].rolling(60).mean()
    row = d.iloc[-1]; close, ma20, ma60 = float(row["close"]), float(row["ma20"]), float(row["ma60"])
    recent_high = float(d["close"].tail(max(60, MARKET.recent_window_bars)).max()); drawdown = close / recent_high - 1.0 if recent_high > 0 else 0.0
    ma20_slope = float(d["ma20"].iloc[-1] - d["ma20"].iloc[-6])
    if drawdown <= MARKET.crash_drawdown_pct and close < ma20: return MarketRegime.CRASH
    if drawdown <= MARKET.weak_drawdown_pct or (close < ma20 and close < ma60): return MarketRegime.WEAK
    if close > ma20 > ma60 and ma20_slope > 0: return MarketRegime.BULLISH
    return MarketRegime.NEUTRAL
