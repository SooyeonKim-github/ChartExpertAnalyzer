from __future__ import annotations

import numpy as np

from ..models import SignalScore


def score_relative_strength(stock_return_pct: float, market_return_pct: float | None) -> SignalScore:
    if market_return_pct is None:
        return SignalScore(None, {"reason": "market_return_unavailable"})
    rs = float(stock_return_pct) - float(market_return_pct)
    score = float(np.clip(50.0 + rs * 6.0, 0.0, 100.0))
    return SignalScore(round(score, 2), {"market_return_pct": round(float(market_return_pct), 3), "rs_pct": round(rs, 3)})
