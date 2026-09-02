from __future__ import annotations

from ..models import SignalScore


def score_price_strength(return_pct: float) -> SignalScore:
    r = float(return_pct)
    if r >= 20:
        score, state = 100.0, "LEADER"
    elif r >= 15:
        score, state = 95.0, "LEADER"
    elif r >= 10:
        score, state = 90.0, "LEADER"
    elif r >= 7:
        score, state = 80.0, "LEADER_CANDIDATE"
    elif r >= 5:
        score, state = 65.0, "LEADER_CANDIDATE"
    elif r >= 3:
        score, state = 40.0, "EARLY"
    elif r > 0:
        score, state = 20.0, "WEAK"
    else:
        score, state = 0.0, "WEAK"
    return SignalScore(score, {"strength_state": state})
