from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import SignalScore


def score_money_flow(
    trading_value: float,
    trading_value_rank: int,
    universe_size: int,
    daily: pd.DataFrame,
    cfg: dict,
) -> SignalScore:
    if universe_size <= 0:
        return SignalScore(None, {"reason": "empty_universe"})

    percentile = 1.0 if universe_size == 1 else 1.0 - (max(trading_value_rank, 1) - 1) / (universe_size - 1)
    rank_score = float(np.clip(percentile, 0.0, 1.0) * 70.0)

    value_cfg = cfg["money_flow"]
    if trading_value >= value_cfg["daily_value_min"]:
        absolute_score = 20.0
    elif trading_value >= value_cfg["daily_value_mid"]:
        absolute_score = 12.0
    elif trading_value >= value_cfg["daily_value_low"]:
        absolute_score = 6.0
    else:
        absolute_score = 0.0

    volume_ratio = None
    volume_score = 0.0
    if daily is not None and len(daily) >= 21 and "volume" in daily:
        base = float(pd.to_numeric(daily["volume"].iloc[-21:-1], errors="coerce").mean())
        cur = float(pd.to_numeric(pd.Series([daily["volume"].iloc[-1]]), errors="coerce").iloc[0])
        if base > 0:
            volume_ratio = cur / base
            if volume_ratio >= 2.0:
                volume_score = 10.0
            elif volume_ratio >= 1.5:
                volume_score = 7.0
            elif volume_ratio >= 1.0:
                volume_score = 3.0

    score = min(100.0, rank_score + absolute_score + volume_score)
    return SignalScore(round(score, 2), {
        "rank_percentile": round(percentile, 4),
        "absolute_score": absolute_score,
        "volume_ratio_20": None if volume_ratio is None else round(volume_ratio, 3),
    })
