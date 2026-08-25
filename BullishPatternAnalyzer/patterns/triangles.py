from __future__ import annotations

import pandas as pd
from config import PATTERN
from core.analysis import breakout_analysis
from core.models import PatternCategory, PatternDetection, PatternState, PatternType
from core.swing_points import find_swing_highs, find_swing_lows, line_fit, line_value
from patterns.base import BasePatternDetector, clamp_score


class AscendingTriangleDetector(BasePatternDetector):
    def detect(self, df: pd.DataFrame) -> PatternDetection | None:
        d = df.tail(PATTERN.triangle_lookback); highs = find_swing_highs(d, PATTERN.swing_order).tail(4); lows = find_swing_lows(d, PATTERN.swing_order).tail(4)
        if len(highs) < 2 or len(lows) < 2: return None
        resistance = float(highs["price"].median()); high_spread = float((highs["price"].max() - highs["price"].min()) / resistance); low_slope, _ = line_fit(lows); rising_pct = float(lows.iloc[-1]["price"] / lows.iloc[0]["price"] - 1.0)
        if high_spread > PATTERN.flat_resistance_tolerance_pct or low_slope <= 0 or rising_pct < PATTERN.triangle_min_rising_low_pct: return None
        structure = 55 + 25 * min(1.0, rising_pct / 0.08) + 20 * max(0.0, 1 - high_spread / PATTERN.flat_resistance_tolerance_pct)
        br = breakout_analysis(df, resistance); state = PatternState.BREAKOUT_CONFIRMED if br["confirmed"] else PatternState.WATCH; support = float(lows.iloc[-1]["price"])
        return PatternDetection(PatternType.ASCENDING_TRIANGLE, PatternCategory.CONTINUATION, state, clamp_score(structure), resistance, support, support, anchors={"highs": highs.to_dict("records"), "lows": lows.to_dict("records")}, metrics={"high_spread_pct": high_spread, "rising_lows_pct": rising_pct}, reasons=["수평 저항대 형성", "저점 상승", "상단 저항 돌파 여부 확인"])


class SymmetricalTriangleDetector(BasePatternDetector):
    def detect(self, df: pd.DataFrame) -> PatternDetection | None:
        d = df.tail(PATTERN.triangle_lookback); highs = find_swing_highs(d, PATTERN.swing_order).tail(4); lows = find_swing_lows(d, PATTERN.swing_order).tail(4)
        if len(highs) < 2 or len(lows) < 2: return None
        hs, hi = line_fit(highs); ls, li = line_fit(lows)
        if not (hs < 0 and ls > 0): return None
        start = int(min(highs.iloc[0]["pos"], lows.iloc[0]["pos"])); end = len(d) - 1; w0 = line_value(hs, hi, start) - line_value(ls, li, start); w1 = line_value(hs, hi, end) - line_value(ls, li, end)
        if w0 <= 0 or w1 <= 0 or w1 >= w0: return None
        resistance = line_value(hs, hi, end); support = line_value(ls, li, end); shrink = 1 - w1 / w0; br = breakout_analysis(df, resistance); state = PatternState.BREAKOUT_CONFIRMED if br["confirmed"] else PatternState.FORMING
        return PatternDetection(PatternType.SYMMETRICAL_TRIANGLE, PatternCategory.DIRECTIONAL, state, clamp_score(55 + 45 * min(1.0, shrink / 0.7)), resistance, support, support, anchors={"highs": highs.to_dict("records"), "lows": lows.to_dict("records")}, metrics={"width_shrink": shrink, "upper_slope": hs, "lower_slope": ls}, reasons=["고점 하락·저점 상승 수렴", "상방 돌파된 경우만 상승 후보로 인정"])
