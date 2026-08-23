from __future__ import annotations
import numpy as np
import pandas as pd

def find_pivots(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.DataFrame:
    out = df.copy()
    highs, lows = out['High'].values, out['Low'].values
    ph = np.full(len(out), np.nan)
    pl = np.full(len(out), np.nan)
    for i in range(left, len(out)-right):
        hs = highs[i-left:i+right+1]
        ls = lows[i-left:i+right+1]
        if highs[i] == np.max(hs):
            ph[i] = highs[i]
        if lows[i] == np.min(ls):
            pl[i] = lows[i]
    out['PIVOT_HIGH'] = ph
    out['PIVOT_LOW'] = pl
    return out

def recent_pivot_points(df: pd.DataFrame, lookback: int = 180):
    x = df.tail(lookback)
    highs = [(i, float(v)) for i,v in enumerate(x['PIVOT_HIGH'].values) if not pd.isna(v)]
    lows = [(i, float(v)) for i,v in enumerate(x['PIVOT_LOW'].values) if not pd.isna(v)]
    return highs, lows
