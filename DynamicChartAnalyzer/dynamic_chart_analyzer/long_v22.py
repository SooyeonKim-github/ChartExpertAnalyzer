from __future__ import annotations

"""Dynamic LONG V2.2: lecture timing preserved, data-driven quality overlay.

The lecture axis is inherited unchanged from V2.1:
    RSI -> MACD -> Ichimoku, with Stage1 -> Stage2 -> Stage3 progression.

Only the secondary quality axis is redesigned.  It answers a different question:
"Among valid lecture signals, which stock/setup should be reviewed first?"

Quality score (0..100):
    Relative Strength 25
    Trend             20
    Price Structure   15
    Volume            15
    Market Context    10  (neutral context tag; no bull/bear direction bet)
    Risk / Chase      15

Market context is deliberately NOT inverted or optimized to the historical sample.
REVERSAL_ENV / NEUTRAL_ENV / TREND_ENV are recorded for later out-of-sample review.
Known market context receives the same neutral 10 points, so it does not alter the
cross-sectional rank.  UNKNOWN receives 5 only to expose incomplete context.
"""

import numpy as np
import pandas as pd

from .long_v21 import score_long_events as _score_long_events_v21


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def _bool(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    return df[col].fillna(False).astype(bool)


def _market_context(market_score: pd.Series) -> np.ndarray:
    return np.select(
        [
            market_score.le(1).fillna(False),
            market_score.between(2, 3, inclusive="both").fillna(False),
            market_score.ge(4).fillna(False),
        ],
        ["REVERSAL_ENV", "NEUTRAL_ENV", "TREND_ENV"],
        default="UNKNOWN",
    )


def _rs_percentile_points(p: pd.Series, *, medium_term: bool) -> np.ndarray:
    """Sweet-spot RS scoring without assuming that the absolute top percentile wins.

    20-day RS prefers the 50~75% band observed to be robust in the development
    sample, while 60-day RS gives the strongest band a little more credit.  Broad
    bands are used deliberately to reduce threshold overfit.
    """
    if medium_term:
        return np.select(
            [
                p.ge(0.75).fillna(False),
                p.between(0.50, 0.75, inclusive="left").fillna(False),
                p.between(0.25, 0.50, inclusive="left").fillna(False),
            ],
            [8.0, 7.0, 4.0],
            default=1.0,
        )
    return np.select(
        [
            p.between(0.50, 0.75, inclusive="left").fillna(False),
            p.between(0.75, 0.90, inclusive="left").fillna(False),
            p.ge(0.90).fillna(False),
            p.between(0.25, 0.50, inclusive="left").fillna(False),
        ],
        [8.0, 6.0, 4.0, 4.0],
        default=1.0,
    )


def score_long_events(
    events: pd.DataFrame,
    confirmed_score: float = 70.0,
    watch_score: float = 55.0,
) -> pd.DataFrame:
    """Preserve lecture score and replace only the secondary quality overlay."""
    out = _score_long_events_v21(
        events,
        confirmed_score=confirmed_score,
        watch_score=watch_score,
    ).copy()

    mask = out["side"].eq("LONG")
    if not mask.any():
        if "market_context" not in out.columns:
            out["market_context"] = ""
        return out

    g = out.loc[mask].copy()

    # ------------------------------------------------------------------
    # Relative Strength: 25
    # ------------------------------------------------------------------
    rs20 = _num(g, "rs_20")
    rs60 = _num(g, "rs_60")
    p20 = _num(g, "rs_percentile_20")
    p60 = _num(g, "rs_percentile_60")

    p20_points = _rs_percentile_points(p20, medium_term=False)      # max 8
    p60_points = _rs_percentile_points(p60, medium_term=True)       # max 8
    rs60_points = np.where(rs60.isna(), 2.5, np.where(rs60 > 0, 5.0, 0.0))
    # A short-term relative pullback is allowed; severe weakness is not rewarded.
    rs20_points = np.where(rs20.isna(), 2.0, np.where(rs20 > -0.03, 4.0, 0.0))
    rs_score = np.clip(p20_points + p60_points + rs60_points + rs20_points, 0, 25)

    # ------------------------------------------------------------------
    # Trend: 20
    # MA20 > MA60 is the main structural condition. Close > MA120 was removed from
    # scoring because it did not improve the development sample and is not lecture
    # logic.  Trend remains a secondary ranking feature only.
    # ------------------------------------------------------------------
    trend_score = (
        _bool(g, "ma20_above_ma60").astype(float).to_numpy() * 10.0
        + (_num(g, "ma60_slope") > 0).astype(float).to_numpy() * 5.0
        + (_num(g, "close_vs_ma60") > 0).astype(float).to_numpy() * 3.0
        + (_num(g, "ma20_slope") > 0).astype(float).to_numpy() * 2.0
    )
    trend_score = np.clip(trend_score, 0, 20)

    # ------------------------------------------------------------------
    # Price Structure: 15
    # Broad sweet spots are intentional: controlled pullback gets the most credit,
    # while a deep >20% pullback still gets some recovery credit but is handled by
    # the separate risk score.
    # ------------------------------------------------------------------
    pullback = _num(g, "pullback_depth")
    distance60 = _num(g, "distance_60d_high")
    close_atr = _num(g, "close_vs_atr")

    pullback_points = np.select(
        [
            pullback.between(0.12, 0.20, inclusive="both").fillna(False),
            pullback.between(0.06, 0.12, inclusive="left").fillna(False),
            pullback.between(0.03, 0.06, inclusive="left").fillna(False),
            pullback.between(0.00, 0.03, inclusive="left").fillna(False),
            pullback.gt(0.20).fillna(False),
        ],
        [8.0, 6.0, 4.0, 3.0, 2.0],
        default=0.0,
    )
    distance_points = np.select(
        [
            distance60.ge(-0.20).fillna(False),
            distance60.ge(-0.30).fillna(False),
        ],
        [4.0, 2.0],
        default=0.0,
    )
    atr_points = np.select(
        [
            close_atr.abs().le(1.5).fillna(False),
            close_atr.abs().le(2.5).fillna(False),
        ],
        [3.0, 1.5],
        default=0.0,
    )
    structure_score = np.clip(pullback_points + distance_points + atr_points, 0, 15)

    # ------------------------------------------------------------------
    # Volume: 15
    # Quality score is intentionally stage-independent.  Moderate contraction and
    # normal/recovering participation are preferred; extreme drying-up or volume
    # explosion do not automatically receive more points.
    # ------------------------------------------------------------------
    contraction = _num(g, "volume_contraction_10d")
    vol5 = _num(g, "volume_ratio_5")
    breakout_vol = _num(g, "breakout_volume_ratio")

    contraction_points = np.select(
        [
            contraction.between(0.70, 0.95, inclusive="both").fillna(False),
            contraction.between(0.95, 1.05, inclusive="right").fillna(False),
            contraction.between(1.05, 1.20, inclusive="right").fillna(False),
        ],
        [8.0, 5.0, 3.0],
        default=0.0,
    )
    vol5_points = np.select(
        [
            vol5.between(0.70, 1.20, inclusive="both").fillna(False),
            vol5.between(1.20, 1.50, inclusive="right").fillna(False),
        ],
        [4.0, 2.0],
        default=0.0,
    )
    breakout_points = np.select(
        [
            breakout_vol.between(0.80, 1.30, inclusive="both").fillna(False),
            breakout_vol.between(1.30, 1.60, inclusive="right").fillna(False),
        ],
        [3.0, 1.0],
        default=0.0,
    )
    volume_score = np.clip(contraction_points + vol5_points + breakout_points, 0, 15)

    # ------------------------------------------------------------------
    # Market Context: 10
    # NO historical reverse-score is applied.  The environment is tagged so later
    # train/validation/OOS analysis can decide whether a regime matters.  All known
    # regimes receive equal neutral credit and therefore do not change ranking.
    # ------------------------------------------------------------------
    market_raw = _num(g, "market_score")
    context = _market_context(market_raw)
    market_score = np.where(pd.isna(market_raw), 5.0, 10.0)

    # ------------------------------------------------------------------
    # Risk / Chase: 15
    # Development data suggested a 6~12% stop distance is a useful broad sweet spot.
    # Chase risk remains a separate penalty-style component.
    # ------------------------------------------------------------------
    stop_distance = _num(g, "stop_distance_pct")
    stop_points = np.select(
        [
            stop_distance.between(0.06, 0.12, inclusive="both").fillna(False),
            stop_distance.lt(0.06).fillna(False),
            stop_distance.between(0.12, 0.15, inclusive="right").fillna(False),
            stop_distance.gt(0.15).fillna(False),
        ],
        [8.0, 6.0, 5.0, 1.0],
        default=4.0,
    )
    chase = g.get("chase_risk", pd.Series("LOW", index=g.index)).astype(str)
    chase_points = np.select(
        [chase.eq("HIGH"), chase.eq("MEDIUM")],
        [0.0, 3.0],
        default=7.0,
    )
    risk_score = np.clip(stop_points + chase_points, 0, 15)

    quality_score = np.clip(
        rs_score
        + trend_score
        + structure_score
        + volume_score
        + market_score
        + risk_score,
        0,
        100,
    )

    # Replace only the secondary-quality components. Lecture columns inherited from
    # V2.1 remain unchanged.
    component_values = {
        "quality_rs_score": rs_score,
        "quality_trend_score": trend_score,
        "quality_price_structure_score": structure_score,
        "quality_volume_score": volume_score,
        "quality_market_score": market_score,
        "quality_risk_score": risk_score,
        "quality_score": quality_score,
        "long_quality_score": quality_score,
    }
    for col, values in component_values.items():
        out.loc[g.index, col] = np.round(np.asarray(values, dtype=float), 2)

    out.loc[g.index, "quality_enhancement_score"] = np.round(quality_score, 2)
    out.loc[g.index, "market_context"] = context

    # Combined is diagnostic only. It never drives Stage, label, or rank.
    lecture = pd.to_numeric(out.loc[g.index, "lecture_score"], errors="coerce").fillna(0).to_numpy()
    combined = np.clip(lecture * 0.60 + quality_score * 0.40, 0, 100)
    out.loc[g.index, "combined_score"] = np.round(combined, 2)

    labels = np.select(
        [quality_score >= confirmed_score, quality_score >= watch_score],
        ["CONFIRMED", "WATCH"],
        default="REJECT",
    )
    out.loc[g.index, "long_quality_label"] = labels

    # Quality ranks lecture-valid entries; lecture score is tie-breaker only.
    ranked = out.loc[mask].sort_values(
        ["signal_date", "quality_score", "lecture_score", "source_rank"],
        ascending=[True, False, False, True],
        kind="stable",
    )
    ranks = ranked.groupby("signal_date").cumcount() + 1
    out.loc[ranked.index, "daily_long_rank"] = ranks.astype("Int64").to_numpy()
    return out
