from __future__ import annotations
import numpy as np
import pandas as pd

def detect_double_bottom_top(df: pd.DataFrame, cfg: dict) -> dict:
    look = df.tail(cfg['pattern_lookback'])
    highs = [(idx,float(v)) for idx,v in zip(look.index, look['PIVOT_HIGH']) if not pd.isna(v)]
    lows = [(idx,float(v)) for idx,v in zip(look.index, look['PIVOT_LOW']) if not pd.isna(v)]
    tol = cfg['level_tolerance_pct']
    result = {'double_bottom': False, 'double_top': False, 'neckline': None, 'pattern_strength': 0.0}
    if len(lows) >= 2:
        (i1,l1),(i2,l2) = lows[-2],lows[-1]
        if i1 < i2 and abs(l2-l1)/max(l1,l2) <= tol:
            between = look.loc[i1:i2]
            neckline = float(between['High'].max())
            result.update(double_bottom=True, neckline=neckline, pattern_strength=max(0,1-abs(l2-l1)/tol/max(l1,l2)))
    if len(highs) >= 2:
        (i1,h1),(i2,h2) = highs[-2],highs[-1]
        if i1 < i2 and abs(h2-h1)/max(h1,h2) <= tol:
            between = look.loc[i1:i2]
            neckline = float(between['Low'].min())
            result.update(double_top=True, neckline=neckline, pattern_strength=max(0,1-abs(h2-h1)/tol/max(h1,h2)))
    return result
