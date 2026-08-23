from __future__ import annotations
import pandas as pd

def detect_head_shoulders(df: pd.DataFrame, cfg: dict) -> dict:
    x = df.tail(cfg['pattern_lookback'])
    highs = [(idx,float(v)) for idx,v in zip(x.index, x['PIVOT_HIGH']) if not pd.isna(v)]
    lows = [(idx,float(v)) for idx,v in zip(x.index, x['PIVOT_LOW']) if not pd.isna(v)]
    out = {'head_shoulders': False, 'inverse_head_shoulders': False, 'neckline': None}
    if len(highs) >= 3:
        a,b,c = highs[-3:]
        shoulder_tol = cfg['level_tolerance_pct'] * 2.5
        shoulders_similar = abs(a[1]-c[1])/max(a[1],c[1]) <= shoulder_tol
        head_higher = b[1] > a[1]*1.03 and b[1] > c[1]*1.03
        if shoulders_similar and head_higher:
            local_lows = [v for idx,v in lows if a[0] <= idx <= c[0]]
            out['head_shoulders'] = True
            out['neckline'] = float(sum(local_lows)/len(local_lows)) if local_lows else None
    if len(lows) >= 3:
        a,b,c = lows[-3:]
        shoulder_tol = cfg['level_tolerance_pct'] * 2.5
        shoulders_similar = abs(a[1]-c[1])/max(a[1],c[1]) <= shoulder_tol
        head_lower = b[1] < a[1]*0.97 and b[1] < c[1]*0.97
        if shoulders_similar and head_lower:
            local_highs = [v for idx,v in highs if a[0] <= idx <= c[0]]
            out['inverse_head_shoulders'] = True
            out['neckline'] = float(sum(local_highs)/len(local_highs)) if local_highs else None
    return out
