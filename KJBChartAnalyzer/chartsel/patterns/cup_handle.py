from __future__ import annotations
import numpy as np
import pandas as pd

def detect_cup_handle(df: pd.DataFrame, cfg: dict) -> dict:
    # 정교한 형태 인식이 아니라 강의의 핵심인 '큰 바닥 후 회복 + 높은 손잡이 저점 + 전고점 재접근'을 근사.
    x = df.tail(cfg['pattern_lookback'])
    if len(x) < 80:
        return {'cup_handle': False}
    n = len(x)
    left = x.iloc[: n//3]
    middle = x.iloc[n//4: 3*n//4]
    right = x.iloc[2*n//3:]
    left_high = float(left['High'].max())
    right_high = float(right['High'].max())
    cup_low = float(middle['Low'].min())
    rim_similarity = abs(right_high-left_high)/max(left_high,right_high)
    depth = (min(left_high,right_high)-cup_low)/max(left_high,right_high)
    recent = x.tail(max(15, n//8))
    handle_low = float(recent['Low'].min())
    handle_high = float(recent['High'].max())
    handle_above_cup = handle_low > cup_low * 1.05
    near_rim = rim_similarity <= 0.08
    valid_depth = 0.10 <= depth <= 0.55
    handle_pullback = handle_low < handle_high * 0.97
    return {
        'cup_handle': bool(near_rim and valid_depth and handle_above_cup and handle_pullback),
        'rim': (left_high+right_high)/2,
        'cup_low': cup_low,
        'handle_low': handle_low,
        'depth_pct': depth,
    }
