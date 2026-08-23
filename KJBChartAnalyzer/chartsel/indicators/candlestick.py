from __future__ import annotations
import pandas as pd

def candle_features(row: pd.Series) -> dict:
    o,h,l,c = map(float, [row['Open'], row['High'], row['Low'], row['Close']])
    rng = max(h-l, 1e-9)
    body = abs(c-o)
    upper = h-max(o,c)
    lower = min(o,c)-l
    return {
        'bullish': c > o,
        'bearish': c < o,
        'body_ratio': body/rng,
        'upper_wick_ratio': upper/rng,
        'lower_wick_ratio': lower/rng,
        'close_location': (c-l)/rng,
        'range': rng,
    }

def detect_candles(df: pd.DataFrame, cfg: dict) -> dict:
    if len(df) < 4:
        return {}
    f0 = candle_features(df.iloc[-1])
    f1 = candle_features(df.iloc[-2])
    f2 = candle_features(df.iloc[-3])
    doji = f0['body_ratio'] <= cfg['doji_body_ratio']
    long_upper = f0['upper_wick_ratio'] >= cfg['long_wick_ratio']
    long_lower = f0['lower_wick_ratio'] >= cfg['long_wick_ratio']
    three_bull = all(candle_features(df.iloc[-i])['bullish'] for i in [1,2,3]) and df['Close'].iloc[-1] > df['Close'].iloc[-2] > df['Close'].iloc[-3]
    three_bear = all(candle_features(df.iloc[-i])['bearish'] for i in [1,2,3]) and df['Close'].iloc[-1] < df['Close'].iloc[-2] < df['Close'].iloc[-3]

    # 강의의 '모닝/이브닝 스타' 설명을 정량화한 근사 규칙.
    morning = (
        f2['bearish'] and f2['body_ratio'] >= 0.50 and
        f1['body_ratio'] <= 0.25 and
        f0['bullish'] and float(df['Close'].iloc[-1]) > (float(df['Open'].iloc[-3]) + float(df['Close'].iloc[-3]))/2
    )
    evening = (
        f2['bullish'] and f2['body_ratio'] >= 0.50 and
        f1['body_ratio'] <= 0.25 and
        f0['bearish'] and float(df['Close'].iloc[-1]) < (float(df['Open'].iloc[-3]) + float(df['Close'].iloc[-3]))/2
    )
    return {
        'doji': doji,
        'long_upper_wick': long_upper,
        'long_lower_wick': long_lower,
        'three_bullish': three_bull,
        'three_bearish': three_bear,
        'morning_star_like': morning,
        'evening_star_like': evening,
        **f0,
    }
