from __future__ import annotations
from ..structure.trend import trend_context

def classify_market_regime(df, ma_cfg: dict) -> str:
    t = trend_context(df, ma_cfg)
    slopes = t['ma_slopes']
    life = ma_cfg['life']; mid = ma_cfg['mid']
    if t['alignment'] == 'bullish_alignment' and slopes[life] > 0 and slopes[mid] > 0:
        return 'uptrend'
    if t['alignment'] == 'bearish_alignment' and slopes[life] < 0 and slopes[mid] < 0:
        return 'downtrend'
    recent_vol = df['Close'].pct_change().tail(20).std()
    if recent_vol > df['Close'].pct_change().tail(120).std() * 1.35:
        return 'volatile'
    return 'range'
