from __future__ import annotations

import numpy as np
import pandas as pd
from config import PATTERN
from core.analysis import breakout_analysis, ma_context
from core.models import PatternCategory, PatternDetection, PatternState, PatternType
from core.swing_points import find_swing_highs, find_swing_lows, line_fit, line_value
from patterns.base import BasePatternDetector, clamp_score


class FallingWedgeDetector(BasePatternDetector):
    def detect(self, df: pd.DataFrame) -> PatternDetection | None:
        d = df.tail(PATTERN.wedge_lookback); highs = find_swing_highs(d, PATTERN.swing_order).tail(4); lows = find_swing_lows(d, PATTERN.swing_order).tail(4)
        if len(highs) < 2 or len(lows) < 2: return None
        hs, hi = line_fit(highs); ls, li = line_fit(lows)
        if not (hs < 0 and ls < 0 and abs(hs) > abs(ls)): return None
        start = int(min(highs.iloc[0]["pos"], lows.iloc[0]["pos"])); end = len(d) - 1; w0 = line_value(hs, hi, start) - line_value(ls, li, start); w1 = line_value(hs, hi, end) - line_value(ls, li, end)
        if w0 <= 0 or w1 <= 0: return None
        shrink = 1 - w1 / w0
        if shrink < PATTERN.wedge_min_width_shrink: return None
        resistance = line_value(hs, hi, end); support = line_value(ls, li, end); br = breakout_analysis(df, resistance); state = PatternState.BREAKOUT_CONFIRMED if br["confirmed"] else PatternState.WATCH
        return PatternDetection(PatternType.FALLING_WEDGE, PatternCategory.REVERSAL, state, clamp_score(55 + 45 * min(1.0, shrink / 0.65)), resistance, support, support, metrics={"width_shrink": shrink, "upper_slope": hs, "lower_slope": ls}, reasons=["하락 쐐기 수렴", "상단 추세선 돌파 시 반전 확인", "상승 다이버전스는 신뢰도 가산 요소"])


class WPatternDetector(BasePatternDetector):
    def detect(self, df: pd.DataFrame) -> PatternDetection | None:
        d = df.tail(PATTERN.w_lookback); lows = find_swing_lows(d, PATTERN.swing_order)
        if len(lows) < 2: return None
        best = None
        for i in range(len(lows) - 1):
            l1, l2 = lows.iloc[i], lows.iloc[i + 1]; sep = int(l2.pos - l1.pos)
            if sep < PATTERN.w_min_separation_bars or sep > PATTERN.w_max_separation_bars: continue
            between = d.iloc[int(l1.pos):int(l2.pos)+1]
            if len(between) < 3: continue
            rebound_pos = int(l1.pos) + int(np.argmax(between["high"].to_numpy())); rebound_high = float(d.iloc[rebound_pos]["high"])
            if rebound_pos in (int(l1.pos), int(l2.pos)) or rebound_high / max(float(l1.price), float(l2.price)) - 1 <= 0.02: continue
            best = (l1, l2, rebound_pos, rebound_high)
        if best is None: return None
        l1, l2, rebound_pos, neckline = best; p1, p2 = float(l1.price), float(l2.price); second_vs_first = p2 / p1 - 1.0
        if second_vs_first < -PATTERN.w_bottom_tolerance_pct: return None
        first_start = max(0, int(l1.pos) - max(5, min(20, int(l1.pos)))); first_decline = d.iloc[first_start:int(l1.pos)+1]; second_decline = d.iloc[rebound_pos:int(l2.pos)+1]
        v1 = float(first_decline["volume"].mean()); v2 = float(second_decline["volume"].mean()); volume_ratio = v2 / v1 if v1 > 0 else np.nan
        slope = lambda seg: float(np.polyfit(np.arange(len(seg)), seg["close"].to_numpy(float), 1)[0]) if len(seg) >= 2 else np.nan
        s1, s2 = slope(first_decline), slope(second_decline); gentler = bool(np.isfinite(s1) and np.isfinite(s2) and abs(s2) < abs(s1)); ma = ma_context(d, int(l2.pos)); ma_dist = ma["ma20_distance_pct"]; ma_close = ma_dist is not None and abs(ma_dist) <= PATTERN.w_ma20_max_distance_pct; higher_low = second_vs_first > 0; vol_contract = np.isfinite(volume_ratio) and volume_ratio <= PATTERN.w_decline_volume_good_ratio
        structure = 45 + (18 if higher_low else 9) + (16 if vol_contract else 7 if np.isfinite(volume_ratio) and volume_ratio <= 1.0 else 0) + (12 if ma_close else 0) + (9 if gentler else 0)
        br = breakout_analysis(df, neckline); state = PatternState.BREAKOUT_CONFIRMED if br["confirmed"] else PatternState.WATCH if (ma["ma5_reclaim"] or ma["ma20_reclaim"] or ma["above_ma20"]) else PatternState.FORMING
        reasons = ["W 패턴 형성"] + (["두 번째 저점이 첫 번째 저점보다 높음"] if higher_low else []) + (["두 번째 하락 거래량 감소"] if vol_contract else []) + (["두 번째 저점과 20일선 이격이 작음"] if ma_close else []) + (["두 번째 하락이 첫 번째보다 완만함"] if gentler else []) + ["첫 반등 고점(넥라인) 돌파 여부 확인"]
        return PatternDetection(PatternType.W_PATTERN, PatternCategory.REVERSAL, state, clamp_score(structure), neckline, p2, p2, anchors={"first_bottom": p1, "rebound_high": neckline, "second_bottom": p2}, metrics={"second_bottom_vs_first_pct": second_vs_first, "second_decline_volume_ratio": None if not np.isfinite(volume_ratio) else volume_ratio, "second_decline_gentler": gentler, "ma20_distance_pct": ma_dist, "ma5_reclaim": ma["ma5_reclaim"], "ma20_reclaim": ma["ma20_reclaim"]}, reasons=reasons)


class InverseHeadShouldersDetector(BasePatternDetector):
    def detect(self, df: pd.DataFrame) -> PatternDetection | None:
        d = df.tail(PATTERN.ihs_lookback); lows = find_swing_lows(d, PATTERN.swing_order)
        if len(lows) < 3: return None
        rows = list(lows.tail(3).itertuples(index=False)); a, h, b = rows; ls, head, rs = float(a.price), float(h.price), float(b.price); shoulder_mean = (ls + rs) / 2
        if abs(ls-rs)/shoulder_mean > PATTERN.ihs_shoulder_tolerance_pct or head > min(ls,rs)*(1-PATTERN.ihs_head_depth_min_pct): return None
        seg1 = d.iloc[int(a.pos):int(h.pos)+1]; seg2 = d.iloc[int(h.pos):int(b.pos)+1]
        if len(seg1) < 2 or len(seg2) < 2: return None
        neckline = (float(seg1["high"].max()) + float(seg2["high"].max())) / 2; br = breakout_analysis(df, neckline); symmetry = 1 - abs(ls-rs)/shoulder_mean; depth = min(ls,rs)/head - 1; structure = 55 + 25*min(1.0, depth/0.12) + 20*symmetry; state = PatternState.BREAKOUT_CONFIRMED if br["confirmed"] else PatternState.WATCH
        return PatternDetection(PatternType.INVERSE_HEAD_SHOULDERS, PatternCategory.REVERSAL, state, clamp_score(structure), neckline, min(ls,rs), head, metrics={"shoulder_difference_pct": abs(ls-rs)/shoulder_mean, "head_depth_pct": depth}, reasons=["역 헤드앤숄더 구조", "머리가 양 어깨보다 낮음", "넥라인 상향 돌파 시 확인"])
