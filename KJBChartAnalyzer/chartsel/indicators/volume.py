from __future__ import annotations
import pandas as pd

def add_volume_features(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    w = cfg['avg_window']
    out['VOL_MA'] = out['Volume'].rolling(w).mean()
    out['REL_VOL'] = out['Volume'] / out['VOL_MA']
    out['RET1'] = out['Close'].pct_change()
    return out

def volume_context(df: pd.DataFrame, cfg: dict) -> dict:
    row = df.iloc[-1]
    rel = float(row.get('REL_VOL', 0) or 0)
    ret = float(row.get('RET1', 0) or 0)
    rng = float((row['High'] - row['Low']) / row['Close']) if row['Close'] else 0.0
    upper_wick = (row['High'] - max(row['Open'], row['Close'])) / max(row['High'] - row['Low'], 1e-9)
    return {
        'relative_volume': rel,
        'price_change': ret,
        'range_pct': rng,
        'bullish_confirm': ret > 0 and rel >= cfg['confirm_ratio'],
        'bearish_confirm': ret < 0 and rel >= cfg['confirm_ratio'],
        'high_volume_stall': abs(ret) < 0.015 and rel >= cfg['strong_ratio'] and rng >= 0.03,
        'distribution_hint': rel >= cfg['strong_ratio'] and upper_wick >= 0.35 and ret <= 0.01,
        'dry_volume': rel <= cfg['dry_ratio'],
    }
