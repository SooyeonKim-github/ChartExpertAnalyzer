from __future__ import annotations
import numpy as np
import pandas as pd
from ..indicators.moving_average import classify_alignment, ma_slope, cross_state

def trend_context(df: pd.DataFrame, ma_cfg: dict) -> dict:
    row = df.iloc[-1]
    alignment = classify_alignment(row, ma_cfg)
    life = ma_cfg['life']; longp = ma_cfg['long']; short = ma_cfg['short']
    close = float(row['Close'])
    life_ma = float(row.get(f'MA{life}', np.nan))
    long_ma = float(row.get(f'MA{longp}', np.nan))
    slopes = {}
    for p in [short, life, ma_cfg['mid'], longp]:
        slopes[p] = ma_slope(df[f'MA{p}'], ma_cfg['slope_lookback'])
    highs = df['PIVOT_HIGH'].dropna().tail(3).values
    lows = df['PIVOT_LOW'].dropna().tail(3).values
    higher_highs = len(highs) >= 2 and highs[-1] > highs[-2]
    higher_lows = len(lows) >= 2 and lows[-1] > lows[-2]
    lower_highs = len(highs) >= 2 and highs[-1] < highs[-2]
    lower_lows = len(lows) >= 2 and lows[-1] < lows[-2]
    life_gap = (close/life_ma-1) if np.isfinite(life_ma) and life_ma else np.nan
    long_gap = (close/long_ma-1) if np.isfinite(long_ma) and long_ma else np.nan
    return {
        'alignment': alignment,
        'above_life_ma': np.isfinite(life_ma) and close > life_ma,
        'above_long_ma': np.isfinite(long_ma) and close > long_ma,
        'ma_slopes': slopes,
        'short_life_cross': cross_state(df, short, life),
        'higher_highs': bool(higher_highs),
        'higher_lows': bool(higher_lows),
        'lower_highs': bool(lower_highs),
        'lower_lows': bool(lower_lows),
        'up_structure': bool(higher_highs and higher_lows),
        'down_structure': bool(lower_highs and lower_lows),
        'life_gap_pct': life_gap,
        'long_gap_pct': long_gap,
        'overextended_life': np.isfinite(life_gap) and life_gap >= ma_cfg.get('distance_warn_life_pct',0.12),
        'overextended_long': np.isfinite(long_gap) and life_gap > 0 and long_gap >= ma_cfg.get('distance_warn_long_pct',0.25),
    }
