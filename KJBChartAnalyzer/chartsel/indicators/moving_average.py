from __future__ import annotations
import pandas as pd

def add_moving_averages(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    periods = [cfg['short'], cfg['life'], cfg['mid'], cfg['long']]
    for p in periods:
        out[f'MA{p}'] = out['Close'].rolling(p).mean()
    return out

def ma_slope(series: pd.Series, lookback: int = 5) -> float:
    s = series.dropna()
    if len(s) <= lookback:
        return 0.0
    prev = float(s.iloc[-lookback-1])
    cur = float(s.iloc[-1])
    if prev == 0:
        return 0.0
    return (cur / prev) - 1.0

def classify_alignment(row: pd.Series, cfg: dict) -> str:
    s, l, m, g = cfg['short'], cfg['life'], cfg['mid'], cfg['long']
    vals = [row.get(f'MA{s}'), row.get(f'MA{l}'), row.get(f'MA{m}'), row.get(f'MA{g}')]
    if any(pd.isna(v) for v in vals):
        return 'unknown'
    if vals[0] > vals[1] > vals[2] > vals[3]:
        return 'bullish_alignment'
    if vals[0] < vals[1] < vals[2] < vals[3]:
        return 'bearish_alignment'
    return 'mixed'

def cross_state(df: pd.DataFrame, fast: int, slow: int) -> str:
    a, b = f'MA{fast}', f'MA{slow}'
    x = df[[a,b]].dropna()
    if len(x) < 2:
        return 'none'
    prev_fast, prev_slow = x.iloc[-2][a], x.iloc[-2][b]
    cur_fast, cur_slow = x.iloc[-1][a], x.iloc[-1][b]
    if prev_fast <= prev_slow and cur_fast > cur_slow:
        return 'golden_cross'
    if prev_fast >= prev_slow and cur_fast < cur_slow:
        return 'dead_cross'
    return 'none'
