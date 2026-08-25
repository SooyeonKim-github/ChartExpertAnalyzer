from __future__ import annotations

import pandas as pd
from config import PATTERN, SCORE
from core.analysis import breakout_analysis, bullish_divergence, momentum_quality, retest_analysis, risk_analysis, volume_quality
from core.models import MarketRegime, PatternDetection, PatternState, RiskLevel
from core.swing_points import find_swing_lows


class BullishPatternScorer:
    def score(self, df: pd.DataFrame, detection: PatternDetection, regime: MarketRegime) -> dict:
        br = breakout_analysis(df, detection.breakout_level); volume = volume_quality(df, detection.breakout_level)
        recent = df.tail(max(PATTERN.ihs_lookback, PATTERN.wedge_lookback)); recent_lows = find_swing_lows(recent, PATTERN.swing_order); low_positions = recent_lows["pos"].astype(int).tail(2).tolist() if len(recent_lows) >= 2 else []; divergence = bullish_divergence(recent, low_positions) if low_positions else False
        momentum = momentum_quality(df, divergence); retest = retest_analysis(df, detection.breakout_level, br["confirmed"]); risk = risk_analysis(df, detection.breakout_level, detection.stop_level)
        selection = 0.45*detection.structure_score + 0.25*br["score"] + 0.15*volume["score"] + 0.15*momentum["score"]
        timing = 0.35*br["score"] + 0.20*volume["score"] + 0.20*momentum["score"] + 0.15*retest["score"] + 10.0*(1 if risk["chase"] == RiskLevel.LOW else 0)
        if regime == MarketRegime.CRASH: timing = min(timing, 45.0)
        elif regime == MarketRegime.WEAK: timing *= 0.85
        state = detection.state
        if br["confirmed"] and retest["valid"]: state = PatternState.RETEST
        if br["confirmed"] and selection >= SCORE.candidate_selection_min and timing >= SCORE.entry_timing_min and risk["chase"] != RiskLevel.HIGH and risk["entry"] != RiskLevel.HIGH and regime != MarketRegime.CRASH: state = PatternState.ENTRY_READY
        return {"state": state, "breakout": br, "volume": volume, "momentum": momentum, "retest": retest, "risk": risk, "divergence": divergence, "selection_score": round(selection,2), "timing_score": round(timing,2)}
