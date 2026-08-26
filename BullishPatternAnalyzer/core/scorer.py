from __future__ import annotations

import pandas as pd

from config import PATTERN, SCORE
from core.analysis import (
    breakout_analysis,
    bullish_divergence,
    indicator_bullish_divergence,
    momentum_quality,
    retest_analysis,
    risk_analysis,
    volume_quality,
)
from core.candle_analysis import analyze_candles
from core.models import DecisionStatus, MarketRegime, PatternDetection, PatternState, RiskLevel
from core.swing_points import find_swing_lows


class BullishPatternScorer:
    def score(self, df: pd.DataFrame, detection: PatternDetection, regime: MarketRegime) -> dict:
        br = breakout_analysis(df, detection.breakout_level)
        volume = volume_quality(df, detection.breakout_level)
        candle = analyze_candles(df, detection.breakout_level)

        recent = df.tail(max(PATTERN.ihs_lookback, PATTERN.wedge_lookback))
        recent_lows = find_swing_lows(recent, PATTERN.swing_order)
        low_positions = recent_lows["pos"].astype(int).tail(2).tolist() if len(recent_lows) >= 2 else []
        divergence = bullish_divergence(recent, low_positions) if low_positions else False
        mfi_divergence = (
            indicator_bullish_divergence(recent, low_positions, "mfi14", 3.0)
            if low_positions
            else False
        )
        momentum = momentum_quality(df, divergence, mfi_divergence)
        retest = retest_analysis(df, detection.breakout_level, br["confirmed"])
        risk = risk_analysis(df, detection.breakout_level, detection.stop_level)

        selection = (
            0.40 * detection.structure_score
            + 0.20 * br["score"]
            + 0.20 * volume["score"]
            + 0.10 * candle["score"]
            + 0.10 * momentum["score"]
        )
        timing = (
            0.30 * br["score"]
            + 0.25 * volume["score"]
            + 0.20 * candle["score"]
            + 0.15 * momentum["score"]
            + 0.10 * retest["score"]
        )
        if risk["chase"] == RiskLevel.LOW:
            timing = min(100.0, timing + 5.0)
        if volume.get("bearish_volume_divergence"):
            timing *= 0.90
        if candle["bearish_warning"]:
            timing *= 0.80
        if regime == MarketRegime.CRASH:
            timing = min(timing, 45.0)
        elif regime == MarketRegime.WEAK:
            timing *= 0.85

        state = detection.state
        if br["confirmed"] and not volume["filter_pass"]:
            state = PatternState.WATCH
        elif br["confirmed"] and volume["filter_pass"] and retest["valid"]:
            state = PatternState.RETEST
        elif br["confirmed"] and volume["filter_pass"]:
            state = PatternState.BREAKOUT_CONFIRMED

        if (
            br["confirmed"]
            and volume["filter_pass"]
            and not candle["bearish_warning"]
            and selection >= SCORE.candidate_selection_min
            and timing >= SCORE.entry_timing_min
            and risk["chase"] != RiskLevel.HIGH
            and risk["entry"] != RiskLevel.HIGH
            and regime != MarketRegime.CRASH
        ):
            state = PatternState.ENTRY_READY

        reject_reasons: list[str] = []
        if detection.state == PatternState.INVALIDATED:
            reject_reasons.append("pattern_invalidated")
        if candle["bearish_warning"]:
            reject_reasons.append("bearish_candle_warning")
        if risk["chase"] == RiskLevel.HIGH:
            reject_reasons.append("high_chase_risk")
        if risk["entry"] == RiskLevel.HIGH:
            reject_reasons.append("high_entry_risk")
        if regime == MarketRegime.CRASH:
            reject_reasons.append("market_crash")

        if reject_reasons:
            decision = DecisionStatus.REJECT
        elif br["confirmed"] and volume["filter_pass"]:
            decision = DecisionStatus.CONFIRMED
        else:
            decision = DecisionStatus.WATCH

        return {
            "state": state,
            "decision_status": decision,
            "reject_reason": ";".join(reject_reasons),
            "breakout": br,
            "volume": volume,
            "candle": candle,
            "momentum": momentum,
            "retest": retest,
            "risk": risk,
            "divergence": divergence,
            "mfi_divergence": mfi_divergence,
            "selection_score": round(selection, 2),
            "timing_score": round(max(0.0, min(100.0, timing)), 2),
        }
