from __future__ import annotations

import math
import pandas as pd

from config import PullbackConfig
from models import ImpulseContext, PullbackContext, SupportContext


def classify(d: pd.DataFrame, impulse: ImpulseContext, pullback: PullbackContext, support: SupportContext,
             components: dict[str, int], score: int, timing_score: int, flags: dict,
             risk: dict, cfg: PullbackConfig):
    warnings: list[str] = []
    close = float(d["Close"].iloc[-1])
    ma60 = float(d["MA60"].iloc[-1]) if pd.notna(d["MA60"].iloc[-1]) else float("nan")
    major_low = float(d["Low"].shift(1).tail(cfg.major_low_lookback_bars).min())
    decisive_ma60_break = bool(math.isfinite(ma60) and close < ma60 * (1 - cfg.decisive_ma60_break_pct / 100.0))
    major_low_break = bool(math.isfinite(major_low) and close < major_low)

    hard_rejects = []
    if not impulse.available:
        hard_rejects.append("NO_VALID_PRIOR_IMPULSE")
    if pullback.available and math.isfinite(pullback.retracement_ratio) and pullback.retracement_ratio > cfg.hard_retracement_max:
        hard_rejects.append("PULLBACK_TOO_DEEP")
    if pullback.high_volume_breakdown and (support.nearest_level != support.nearest_level or close < support.nearest_level):
        hard_rejects.append("HIGH_VOLUME_BREAKDOWN")
    if decisive_ma60_break:
        hard_rejects.append("MA60_DECISIVE_BREAK")
    if major_low_break:
        hard_rejects.append("MAJOR_LOW_BREAK")
    if pullback.midpoint_broken and not flags.get("minor_high_breakout"):
        hard_rejects.append("IMPULSE_MIDPOINT_BROKEN")

    confirmation_trigger = bool(
        flags.get("minor_high_breakout")
        or flags.get("ma_reclaim")
        or (flags.get("bullish_reversal") and support.support_held
            and flags.get("confirmation_volume_ratio", 0) >= cfg.confirmation_volume_ratio)
    )
    core_setup_ok = bool(
        components.get("Impulse", 0) >= cfg.min_impulse_score_confirmed
        and components.get("Pullback", 0) >= cfg.min_pullback_score_confirmed
        and components.get("Volume", 0) >= cfg.min_volume_score_confirmed
        and components.get("Confirmation", 0) >= cfg.min_confirmation_score_confirmed
    )

    if hard_rejects:
        warnings.extend(hard_rejects)
        return "REJECT", hard_rejects[0], warnings

    if (score >= cfg.confirmed_score and timing_score >= cfg.confirmed_timing_score
            and core_setup_ok and confirmation_trigger and not risk.get("chase_risk", False)):
        if flags.get("minor_high_breakout"):
            primary = "FIRST_PULLBACK_BREAKOUT_CONFIRMED" if pullback.sequence == 1 else "PULLBACK_BREAKOUT_CONFIRMED"
        elif flags.get("ma_reclaim"):
            primary = "MA_RECLAIM_CONFIRMED"
        else:
            primary = "SUPPORT_REVERSAL_CONFIRMED"
        return "CONFIRMED", primary, warnings

    if score >= cfg.watch_score:
        if risk.get("chase_risk", False):
            primary = "CHASE_RISK_WATCH"
        elif not confirmation_trigger:
            primary = "WAITING_CONFIRMATION"
        elif timing_score < cfg.confirmed_timing_score:
            primary = "TIMING_NOT_READY"
        else:
            primary = "PULLBACK_SETUP_WATCH"
        return "WATCH", primary, warnings

    return "REJECT", "PULLBACK_QUALITY_INSUFFICIENT", warnings
