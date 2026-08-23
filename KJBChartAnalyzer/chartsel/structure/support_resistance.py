from __future__ import annotations
from typing import List
import numpy as np
import pandas as pd

def _cluster_levels(values: List[float], tolerance_pct: float, min_touches: int) -> List[float]:
    vals = sorted([float(v) for v in values if np.isfinite(v)])
    clusters: list[list[float]] = []
    for v in vals:
        placed = False
        for c in clusters:
            center = float(np.mean(c))
            if center and abs(v-center)/center <= tolerance_pct:
                c.append(v); placed = True; break
        if not placed:
            clusters.append([v])
    levels = [float(np.mean(c)) for c in clusters if len(c) >= min_touches]
    return sorted(levels)

def support_resistance(df: pd.DataFrame, cfg: dict) -> dict:
    x = df.tail(cfg['pattern_lookback'])
    supports = _cluster_levels(x['PIVOT_LOW'].dropna().tolist(), cfg['level_tolerance_pct'], cfg['min_level_touches'])
    resistances = _cluster_levels(x['PIVOT_HIGH'].dropna().tolist(), cfg['level_tolerance_pct'], cfg['min_level_touches'])
    close = float(df['Close'].iloc[-1])
    below = sorted([v for v in supports + resistances if v <= close], reverse=True)
    above = sorted([v for v in supports + resistances if v > close])
    nearest_support = below[0] if below else None
    nearest_resistance = above[0] if above else None
    return {
        'supports': supports,
        'resistances': resistances,
        'nearest_support': nearest_support,
        'nearest_resistance': nearest_resistance,
    }

def breakout_retest_state(df: pd.DataFrame, levels: dict, cfg: dict) -> dict:
    close = float(df['Close'].iloc[-1]); prev = float(df['Close'].iloc[-2])
    buffer = cfg['breakout_buffer_pct']
    breakout = None
    for level in sorted(levels['resistances']):
        if prev <= level*(1+buffer) and close > level*(1+buffer):
            breakout = level
    breakdown = None
    for level in sorted(levels['supports'], reverse=True):
        if prev >= level*(1-buffer) and close < level*(1-buffer):
            breakdown = level
    retest_support = None
    recent = df.tail(10)
    for level in levels['resistances']:
        crossed_before = bool((recent['Close'].iloc[:-1] > level*(1+buffer)).any())
        if crossed_before and abs(close-level)/close <= cfg['level_tolerance_pct'] and close >= level:
            retest_support = level
    return {'breakout_level': breakout, 'breakdown_level': breakdown, 'retest_support_level': retest_support}
