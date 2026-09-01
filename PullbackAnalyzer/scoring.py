from __future__ import annotations

import math
import numpy as np
import pandas as pd

from config import PullbackConfig
from models import ImpulseContext, MarketContext, PullbackContext, SupportContext


def _finite(v) -> bool:
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


def score_setup(d: pd.DataFrame, impulse: ImpulseContext, pullback: PullbackContext, support: SupportContext,
                market: MarketContext, risk: dict, cfg: PullbackConfig):
    reasons: list[str] = []
    warnings: list[str] = []
    components = {"Impulse": 0, "Trend": 0, "Pullback": 0, "Volume": 0,
                  "Support": 0, "Confirmation": 0, "Market_Risk": 0}
    cur = d.iloc[-1]
    prev = d.iloc[-2]
    close = float(cur["Close"])
    bullish = close > float(cur["Open"])

    if impulse.available:
        r = impulse.return_pct
        components["Impulse"] += 5 if r >= cfg.impulse_strong_return_pct else (4 if r >= 15 else (2 if r >= cfg.impulse_min_return_pct else 0))
        components["Impulse"] += 5 if impulse.volume_ratio >= cfg.impulse_volume_ratio_strong else (4 if impulse.volume_ratio >= 1.5 else (2 if impulse.volume_ratio >= cfg.impulse_volume_ratio_min else 0))
        components["Impulse"] += 5 if impulse.breakout else (3 if impulse.body_atr >= 1.0 else 0)
        reasons.append(f"선행 상승 {r:.1f}% / 기준봉 거래량 {impulse.volume_ratio:.2f}배")
    else:
        warnings.append("유효한 선행 상승/기준봉 없음")

    ma20 = float(cur["MA20"]) if pd.notna(cur["MA20"]) else np.nan
    ma60 = float(cur["MA60"]) if pd.notna(cur["MA60"]) else np.nan
    if _finite(ma20) and _finite(ma60):
        components["Trend"] += 6 if close > ma20 > ma60 else (5 if close > ma20 and close > ma60 else (3 if close > ma60 else 0))
    slope_n = cfg.ma_slope_lookback_bars
    ma20_prev = float(d["MA20"].iloc[-1-slope_n]) if len(d) > slope_n and pd.notna(d["MA20"].iloc[-1-slope_n]) else np.nan
    ma60_prev = float(d["MA60"].iloc[-1-slope_n]) if len(d) > slope_n and pd.notna(d["MA60"].iloc[-1-slope_n]) else np.nan
    ma20_up = _finite(ma20_prev) and ma20 > ma20_prev
    ma60_up = _finite(ma60_prev) and ma60 > ma60_prev
    components["Trend"] += 2 if ma20_up else 0
    components["Trend"] += 2 if ma60_up else 0
    if pullback.higher_low:
        components["Trend"] += 3
        reasons.append("Higher Low 유지")
    ma120 = float(cur["MA120"]) if pd.notna(cur["MA120"]) else np.nan
    ma224 = float(cur["MA224"]) if pd.notna(cur["MA224"]) else np.nan
    if (_finite(ma224) and close > ma224) or (_finite(ma120) and close > ma120):
        components["Trend"] += 2

    if pullback.available:
        seq = pullback.sequence
        components["Pullback"] += 6 if seq == 1 else (4 if seq == 2 else (2 if seq == 3 else 0))
        rr = pullback.retracement_ratio
        if _finite(rr):
            components["Pullback"] += 5 if rr <= cfg.ideal_retracement_max else (4 if rr <= cfg.acceptable_retracement_max else (2 if rr <= 0.50 else 0))
        if pullback.period_correction:
            components["Pullback"] += 4
            reasons.append("얕은 가격 하락 + 기간 조정")
        elif pullback.bars >= 3:
            components["Pullback"] += 2
        components["Pullback"] += 2 if pullback.atr_contraction else 0
        components["Pullback"] += 1 if pullback.range_contraction else 0
        if pullback.price_stopping:
            components["Pullback"] += 2
            reasons.append("최근 저점/종가 하락 둔화")
        if pullback.midpoint_broken:
            warnings.append("상승폭 허리(50%) 하향 이탈")

    vr = pullback.volume_ratio_impulse
    if _finite(vr):
        components["Volume"] += 7 if vr <= 0.40 else (6 if vr <= 0.55 else (4 if vr <= 0.70 else (2 if vr <= 0.85 else 0)))
        if vr <= 0.70:
            reasons.append(f"눌림 거래량 감소({vr:.2f}× impulse)")
    if not pullback.high_volume_breakdown:
        components["Volume"] += 4
    else:
        warnings.append("조정 중 고거래량 장대음봉 존재")
    confirmation_vol = float(cur["Volume"] / d["Volume"].iloc[-6:-1].mean()) if len(d) >= 6 and d["Volume"].iloc[-6:-1].mean() > 0 else np.nan
    if bullish and _finite(confirmation_vol):
        if confirmation_vol >= cfg.confirmation_volume_ratio:
            components["Volume"] += 4
            reasons.append("반전봉 거래량 재증가")
        elif confirmation_vol >= 0.9:
            components["Volume"] += 2

    if support.near_ma:
        components["Support"] += 5
    elif _finite(support.distance_pct) and support.distance_pct <= cfg.support_max_pct:
        components["Support"] += 3
    if support.near_price_level:
        components["Support"] += 5
    elif support.confluence_count >= 2:
        components["Support"] += 4
    components["Support"] += 3 if support.bb_support else 0
    if support.touch_count <= 2:
        components["Support"] += 2
    elif support.touch_count == 3:
        components["Support"] += 1
    else:
        warnings.append(f"지지선 반복 테스트 {support.touch_count}회")

    local_high = float(d["High"].iloc[-1-cfg.local_high_lookback_bars:-1].max()) if len(d) > cfg.local_high_lookback_bars else float(prev["High"])
    minor_breakout = bool(bullish and close > local_high)
    ma10 = float(cur["MA10"]) if pd.notna(cur["MA10"]) else np.nan
    prev_ma10 = float(prev["MA10"]) if pd.notna(prev["MA10"]) else np.nan
    ma_reclaim = bool(_finite(ma10) and _finite(prev_ma10) and float(prev["Close"]) <= prev_ma10 and close > ma10)
    lower_wick_reversal = bool(bullish and pd.notna(cur["Close_Location"]) and float(cur["Close_Location"]) >= 0.70)
    components["Confirmation"] += 3 if bullish else 0
    if minor_breakout:
        components["Confirmation"] += 4
        reasons.append("눌림 단기 고점 재돌파")
    if ma_reclaim:
        components["Confirmation"] += 3
        reasons.append("MA10 reclaim")
    elif lower_wick_reversal:
        components["Confirmation"] += 2

    if market.available:
        components["Market_Risk"] += 3 if market.regime == "uptrend" else (1 if market.regime == "range" else 0)
        components["Market_Risk"] += 4 if market.rs_score >= 75 else (3 if market.rs_score >= 60 else (2 if market.rs_score >= 50 else 0))
    else:
        components["Market_Risk"] += 2
        warnings.append("시장지수/상대강도 데이터 사용 불가")
    if not risk.get("chase_risk", False):
        components["Market_Risk"] += 3
    else:
        warnings.append("이격 또는 손절거리 과다")

    caps = {"Impulse": 15, "Trend": 15, "Pullback": 20, "Volume": 15,
            "Support": 15, "Confirmation": 10, "Market_Risk": 10}
    for k, cap in caps.items():
        components[k] = int(min(cap, max(0, components[k])))
    score = int(sum(components.values()))

    timing = 0
    timing += 20 if (_finite(support.distance_pct) and support.distance_pct <= cfg.support_near_pct) else 0
    timing += 15 if pullback.price_stopping else 0
    timing += 15 if bullish else 0
    timing += 15 if ma_reclaim else 0
    timing += 20 if minor_breakout else 0
    timing += 10 if (bullish and _finite(confirmation_vol) and confirmation_vol >= cfg.confirmation_volume_ratio) else 0
    timing += 5 if (_finite(risk.get("stop_distance_pct")) and risk["stop_distance_pct"] <= 5.0) else 0
    timing = int(min(100, timing))

    flags = {
        "bullish_reversal": bullish, "minor_high_breakout": minor_breakout,
        "ma_reclaim": ma_reclaim, "lower_wick_reversal": lower_wick_reversal,
        "confirmation_volume_ratio": confirmation_vol, "local_high": local_high,
    }
    return components, score, timing, flags, reasons, warnings
