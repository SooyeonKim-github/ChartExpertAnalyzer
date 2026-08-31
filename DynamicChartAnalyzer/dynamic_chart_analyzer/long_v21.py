from __future__ import annotations

"""Lecture/quality split scoring for Dynamic LONG V2.1.

This module deliberately separates two different questions:

1. lecture_score (0..100): how far the signal agrees with the lecture's
   RSI -> MACD -> Ichimoku confirmation logic.
2. quality_score (0..100): how attractive the stock/setup is using secondary
   research features (trend, relative strength, volume, price structure,
   market context, risk/chase).

Stage remains the chronological state-machine state and is not replaced by either
score. `long_quality_score` is kept as a backward-compatible alias of
`quality_score`. `combined_score` is diagnostic only and is not used for labels or
ranking.
"""

import numpy as np
import pandas as pd

from .long_v2 import score_long_events as _score_long_events_60_40


def score_long_events(
    events: pd.DataFrame,
    confirmed_score: float = 70.0,
    watch_score: float = 55.0,
) -> pd.DataFrame:
    """Return split 0..100 lecture and secondary-quality scores.

    The existing V2 component model remains the calculation source:
      lecture core: RSI 15 + MACD 20 + Ichimoku 25 = 60 raw points
      secondary quality: Trend 10 + RS 10 + Volume 5 + Price Structure 5
                         + Market 5 + Risk/Chase 5 = 40 raw points

    V2.1 normalizes those two axes independently so a Stage-1 setup can be judged
    as a high-quality early setup without being automatically rejected merely
    because MACD/Ichimoku confirmations have not happened yet.
    """
    out = _score_long_events_60_40(
        events,
        confirmed_score=confirmed_score,
        watch_score=watch_score,
    ).copy()

    mask = out["side"].eq("LONG")
    if not mask.any():
        for col in [
            "lecture_core_score_60",
            "quality_enhancement_score_40",
            "quality_score",
            "combined_score",
        ]:
            if col not in out.columns:
                out[col] = np.nan
        return out

    raw_lecture = pd.to_numeric(out.loc[mask, "lecture_score"], errors="coerce").clip(0, 60)
    raw_quality = pd.to_numeric(
        out.loc[mask, "quality_enhancement_score"], errors="coerce"
    ).clip(0, 40)

    out.loc[mask, "lecture_core_score_60"] = raw_lecture
    out.loc[mask, "quality_enhancement_score_40"] = raw_quality

    lecture_score = (raw_lecture / 60.0 * 100.0).clip(0, 100)
    quality_score = (raw_quality / 40.0 * 100.0).clip(0, 100)
    combined_score = (lecture_score * 0.60 + quality_score * 0.40).clip(0, 100)

    # Public normalized axes.
    out.loc[mask, "lecture_score"] = np.round(lecture_score, 2)
    out.loc[mask, "quality_score"] = np.round(quality_score, 2)
    out.loc[mask, "combined_score"] = np.round(combined_score, 2)

    # Backward compatibility: existing CSV/report consumers can still use
    # long_quality_score, but it now means secondary quality only.
    out.loc[mask, "long_quality_score"] = np.round(quality_score, 2)

    # CONFIRMED/WATCH/REJECT is intentionally based only on secondary quality.
    # Stage already expresses lecture progression; folding lecture progression into
    # the label would recreate the Stage-3 structural bias V2.1 is designed to avoid.
    q = quality_score.to_numpy(dtype=float)
    labels = np.select(
        [q >= confirmed_score, q >= watch_score],
        ["CONFIRMED", "WATCH"],
        default="REJECT",
    )
    out.loc[mask, "long_quality_label"] = labels

    # Rank today's LONGs by setup quality first. Lecture score is only a tie-breaker,
    # and source_rank is the final deterministic tie-breaker.
    ranked = out.loc[mask].sort_values(
        ["signal_date", "quality_score", "lecture_score", "source_rank"],
        ascending=[True, False, False, True],
        kind="stable",
    )
    ranks = ranked.groupby("signal_date").cumcount() + 1
    out.loc[ranked.index, "daily_long_rank"] = ranks.astype("Int64").to_numpy()
    return out
