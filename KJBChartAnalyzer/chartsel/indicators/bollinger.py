from __future__ import annotations
import numpy as np
import pandas as pd

def add_bollinger(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    w = cfg['window']
    k = cfg['std_mult']
    mid = out['Close'].rolling(w).mean()
    std = out['Close'].rolling(w).std(ddof=0)
    out['BB_MID'] = mid
    out['BB_UPPER'] = mid + k*std
    out['BB_LOWER'] = mid - k*std
    out['BB_WIDTH'] = (out['BB_UPPER'] - out['BB_LOWER']) / out['BB_MID']
    out['BB_PCT'] = (out['Close'] - out['BB_LOWER']) / (out['BB_UPPER'] - out['BB_LOWER'])
    return out

def bollinger_context(df: pd.DataFrame, cfg: dict) -> dict:
    row = df.iloc[-1]
    width = float(row.get('BB_WIDTH', np.nan))
    hist = df['BB_WIDTH'].dropna().tail(cfg['squeeze_lookback'])
    if len(hist) >= 20 and np.isfinite(width):
        threshold = float(hist.quantile(cfg['squeeze_percentile']))
        squeeze = width <= threshold
    else:
        threshold, squeeze = np.nan, False
    close = float(row['Close'])
    upper = float(row.get('BB_UPPER', np.nan))
    lower = float(row.get('BB_LOWER', np.nan))
    mid = float(row.get('BB_MID', np.nan))
    recent = df.tail(5)
    upper_walk = bool((recent['Close'] >= recent['BB_UPPER']*0.985).sum() >= 3) if 'BB_UPPER' in recent else False
    lower_walk = bool((recent['Close'] <= recent['BB_LOWER']*1.015).sum() >= 3) if 'BB_LOWER' in recent else False
    return {
        'squeeze': squeeze,
        'width': width,
        'squeeze_threshold': threshold,
        'near_upper': np.isfinite(upper) and close >= upper*0.99,
        'near_lower': np.isfinite(lower) and close <= lower*1.01,
        'above_mid': np.isfinite(mid) and close > mid,
        'upper_band_walk': upper_walk,
        'lower_band_walk': lower_walk,
    }
