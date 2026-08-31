from __future__ import annotations

import numpy as np
import pandas as pd


BENCHMARK_PROXY = {
    "KOSPI": "069500",   # KODEX 200
    "KOSDAQ": "229200",  # KODEX KOSDAQ 150
}

BASE_EVENT_FEATURE_COLUMNS = [
    # RSI / lecture state
    "rsi",
    "rsi_prev",
    "rsi_min_10d",
    "rsi_rebound_strength",
    "bullish_divergence_recent",
    # MACD / lecture state
    "macd",
    "macd_signal",
    "macd_hist",
    "macd_hist_slope",
    "macd_distance_from_zero",
    "macd_golden_below_zero",
    "macd_hist_rising",
    # Trend
    "close_vs_ma20",
    "close_vs_ma60",
    "close_vs_ma120",
    "ma20_slope",
    "ma60_slope",
    "ma20_above_ma60",
    # Volume
    "volume_ratio_20",
    "volume_ratio_5",
    "volume_contraction_10d",
    "breakout_volume_ratio",
    # Relative strength (percentiles are added cross-sectionally later)
    "rs_20",
    "rs_60",
    # Price structure
    "distance_20d_high",
    "distance_60d_high",
    "pullback_depth",
    "atr_pct",
    "close_vs_atr",
    # Ichimoku / lecture state
    "cloud_distance",
    "cloud_thickness",
    "tenkan_kijun_gap",
    "cloud_retest",
    "tenkan_above_kijun",
    "above_cloud",
    "chikou_bullish",
    "doji_risk",
    # Market
    "market_ret20",
    "market_ret60",
    "market_above_ma60",
    "market_score",
    "market_regime",
    # Risk
    "stop_distance_pct",
    "chase_risk_score",
    "chase_risk",
]

RS_PERCENTILE_COLUMNS = ["rs_percentile_20", "rs_percentile_60"]

LONG_V2_OUTPUT_COLUMNS = [
    "lecture_score",
    "lecture_rsi_score",
    "lecture_macd_score",
    "lecture_ichimoku_score",
    "quality_enhancement_score",
    "quality_trend_score",
    "quality_rs_score",
    "quality_volume_score",
    "quality_price_structure_score",
    "quality_market_score",
    "quality_risk_score",
    "long_quality_score",
    "long_quality_label",
    "daily_long_rank",
]


def _safe_ratio(numer: pd.Series, denom: pd.Series) -> pd.Series:
    return numer / denom.replace(0, np.nan)


def prepare_market_features(benchmark_ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Build causal market-regime features from a liquid market ETF proxy."""
    m = benchmark_ohlcv.copy()
    m.index = pd.to_datetime(m.index)
    m = m.sort_index()
    close = pd.to_numeric(m["close"], errors="coerce")

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma60_slope = ma60 / ma60.shift(5) - 1.0

    score = (
        (close > ma20).astype(int)
        + (close > ma60).astype(int)
        + (ma20 > ma60).astype(int)
        + (ma60_slope > 0).astype(int)
        + (close.pct_change(20) > 0).astype(int)
    )
    regime = pd.Series(
        np.select(
            [score >= 4, score <= 1],
            ["BULL", "BEAR"],
            default="NEUTRAL",
        ),
        index=m.index,
        dtype="object",
    )

    return pd.DataFrame(
        {
            "market_ret20": close.pct_change(20),
            "market_ret60": close.pct_change(60),
            "market_above_ma60": close > ma60,
            "market_score": score.astype(float),
            "market_regime": regime,
        },
        index=m.index,
    )


def add_long_v2_features(
    analyzed: pd.DataFrame,
    market_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add LONG V2 research features without changing Stage1/2/3 signal logic."""
    out = analyzed.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()

    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce")

    # RSI
    out["rsi_prev"] = out["rsi"].shift(1)
    out["rsi_min_10d"] = out["rsi"].rolling(10, min_periods=3).min()
    out["rsi_rebound_strength"] = out["rsi"] - out["rsi_min_10d"]
    if "bullish_divergence_recent" not in out.columns:
        out["bullish_divergence_recent"] = False

    # MACD
    out["macd_hist_slope"] = out["macd_hist"] - out["macd_hist"].shift(1)
    out["macd_distance_from_zero"] = _safe_ratio(out["macd"], close)
    if "macd_golden_below_zero" not in out.columns:
        out["macd_golden_below_zero"] = False
    if "macd_hist_rising" not in out.columns:
        out["macd_hist_rising"] = out["macd_hist_slope"] > 0

    # Trend
    out["ma20"] = close.rolling(20).mean()
    out["ma60"] = close.rolling(60).mean()
    out["ma120"] = close.rolling(120).mean()
    out["close_vs_ma20"] = _safe_ratio(close, out["ma20"]) - 1.0
    out["close_vs_ma60"] = _safe_ratio(close, out["ma60"]) - 1.0
    out["close_vs_ma120"] = _safe_ratio(close, out["ma120"]) - 1.0
    out["ma20_slope"] = _safe_ratio(out["ma20"], out["ma20"].shift(5)) - 1.0
    out["ma60_slope"] = _safe_ratio(out["ma60"], out["ma60"].shift(5)) - 1.0
    out["ma20_above_ma60"] = out["ma20"] > out["ma60"]

    # Volume
    vol5 = volume.rolling(5).mean()
    vol10 = volume.rolling(10).mean()
    vol20 = volume.rolling(20).mean()
    out["volume_ratio_20"] = _safe_ratio(volume, vol20)
    out["volume_ratio_5"] = _safe_ratio(volume, vol5)
    out["volume_contraction_10d"] = _safe_ratio(vol10, vol20)
    out["breakout_volume_ratio"] = _safe_ratio(volume, vol20.shift(1))

    # Price structure
    high20 = pd.to_numeric(out["high"], errors="coerce").rolling(20).max()
    high60 = pd.to_numeric(out["high"], errors="coerce").rolling(60).max()
    out["distance_20d_high"] = _safe_ratio(close, high20) - 1.0
    out["distance_60d_high"] = _safe_ratio(close, high60) - 1.0
    out["pullback_depth"] = 1.0 - _safe_ratio(close, high20)
    out["atr_pct"] = _safe_ratio(out["atr"], close)
    out["close_vs_atr"] = (close - out["ma20"]) / out["atr"].replace(0, np.nan)

    # Ichimoku
    cloud_top = pd.to_numeric(out["cloud_top"], errors="coerce")
    cloud_bottom = pd.to_numeric(out["cloud_bottom"], errors="coerce")
    out["cloud_distance"] = np.select(
        [close > cloud_top, close < cloud_bottom],
        [
            (close - cloud_top) / close.replace(0, np.nan),
            (close - cloud_bottom) / close.replace(0, np.nan),
        ],
        default=0.0,
    )
    out["cloud_thickness"] = _safe_ratio(out["cloud_width"], close)
    out["tenkan_kijun_gap"] = (out["tenkan"] - out["kijun"]) / close.replace(0, np.nan)
    out["cloud_retest"] = out.get("cloud_retest_hold", False)
    out["tenkan_above_kijun"] = out["tenkan"] > out["kijun"]
    if "above_cloud" not in out.columns:
        out["above_cloud"] = close > cloud_top
    if "chikou_bullish" not in out.columns:
        chikou_ref = out.get("chikou_reference_price", close.shift(26))
        out["chikou_bullish"] = close > chikou_ref
    if "doji_risk" not in out.columns:
        candle_range = (out["high"] - out["low"]).replace(0, np.nan)
        out["doji_risk"] = ((out["close"] - out["open"]).abs() / candle_range) <= 0.1

    # Market + Relative Strength
    if market_features is not None and not market_features.empty:
        mf = market_features.reindex(out.index).ffill(limit=3)
        for col in [
            "market_ret20",
            "market_ret60",
            "market_above_ma60",
            "market_score",
            "market_regime",
        ]:
            out[col] = mf[col]
    else:
        out["market_ret20"] = np.nan
        out["market_ret60"] = np.nan
        out["market_above_ma60"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
        out["market_score"] = np.nan
        out["market_regime"] = "UNKNOWN"

    out["stock_ret20"] = close.pct_change(20)
    out["stock_ret60"] = close.pct_change(60)
    out["rs_20"] = out["stock_ret20"] - out["market_ret20"]
    out["rs_60"] = out["stock_ret60"] - out["market_ret60"]

    # Risk / chase
    stop = pd.to_numeric(out.get("long_stop_reference"), errors="coerce")
    out["stop_distance_pct"] = (close - stop) / close.replace(0, np.nan)
    out.loc[(stop <= 0) | (stop >= close), "stop_distance_pct"] = np.nan

    ret5 = close.pct_change(5)
    chase_score = (
        (ret5 >= 0.15).astype(int)
        + (out["close_vs_ma20"] >= 0.10).astype(int)
        + (out["close_vs_atr"] >= 2.5).astype(int)
        + (out["rsi"] >= 75).astype(int)
    )
    out["chase_risk_score"] = chase_score
    out["chase_risk"] = np.select(
        [chase_score >= 3, chase_score == 2],
        ["HIGH", "MEDIUM"],
        default="LOW",
    )
    return out


def add_rs_percentiles(panel: pd.DataFrame) -> pd.DataFrame:
    """Add date-wise cross-sectional RS percentiles across the full universe."""
    if panel.empty:
        return panel.copy()
    out = panel.copy()
    out["signal_date"] = pd.to_datetime(out["signal_date"])
    out["rs_percentile_20"] = out.groupby("signal_date")["rs_20"].rank(method="average", pct=True)
    out["rs_percentile_60"] = out.groupby("signal_date")["rs_60"].rank(method="average", pct=True)
    return out


def _bool_score(series: pd.Series, points: float) -> pd.Series:
    return series.fillna(False).astype(bool).astype(float) * points


def _tier_score(values: pd.Series, rules: list[tuple[float, float]]) -> np.ndarray:
    """Score descending lower-bound tiers: [(threshold, points), ...]."""
    x = pd.to_numeric(values, errors="coerce")
    score = np.zeros(len(x), dtype=float)
    remaining = np.ones(len(x), dtype=bool)
    for threshold, points in rules:
        hit = remaining & x.ge(threshold).fillna(False).to_numpy()
        score[hit] = points
        remaining &= ~hit
    return score


def score_long_events(
    events: pd.DataFrame,
    confirmed_score: float = 70.0,
    watch_score: float = 55.0,
) -> pd.DataFrame:
    """Score LONG entries with lecture logic as the 60-point core.

    Score architecture:
      Core Lecture Score 60 = RSI 15 + MACD 20 + Ichimoku 25
      Quality Enhancement 40 = Trend 10 + RS 10 + Volume 5 + Price Structure 5
                               + Market 5 + Risk/Chase 5

    Stage remains a chronological confirmation state. The score does not change the
    original Stage1 -> Stage2 -> Stage3 state machine or the fixed 1:2:7 entry plan.
    """
    out = events.copy()
    score_cols = [
        "lecture_score",
        "lecture_rsi_score",
        "lecture_macd_score",
        "lecture_ichimoku_score",
        "quality_enhancement_score",
        "quality_trend_score",
        "quality_rs_score",
        "quality_volume_score",
        "quality_price_structure_score",
        "quality_market_score",
        "quality_risk_score",
        "long_quality_score",
    ]
    for col in score_cols:
        out[col] = np.nan
    out["long_quality_label"] = ""
    out["daily_long_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")

    mask = out["side"].eq("LONG")
    if not mask.any():
        return out

    g = out.loc[mask].copy()
    stage = pd.to_numeric(g["stage"], errors="coerce").fillna(0)

    # ------------------------------------------------------------------
    # Core Lecture Score: 60
    # ------------------------------------------------------------------
    # RSI 15: Stage1 itself is the lecture's oversold-zone recovery trigger.
    # Later stages can only exist after Stage1 in the state machine, so they retain
    # that confirmation credit. Divergence/rebound strength add quality within RSI.
    rsi_score = (
        _bool_score(stage >= 1, 10)
        + _bool_score(g["rsi_rebound_strength"] >= 5.0, 2)
        + _bool_score(g["bullish_divergence_recent"], 3)
    )

    # MACD 20: Stage2 means a valid below-zero golden cross + rising histogram under
    # the existing lecture-based signal definition. Stage1 may receive only early
    # improvement credit before the formal Stage2 confirmation occurs.
    macd_score = (
        _bool_score(stage >= 2, 12)
        + _bool_score(g["macd_hist_slope"] > 0, 4)
        + _bool_score(g["macd"] < 0, 2)
        + _bool_score(g["macd_hist_rising"], 2)
    )
    macd_score = np.minimum(np.asarray(macd_score, dtype=float), 20.0)

    # Ichimoku 25: use exactly the lecture concepts already used by Stage3:
    # Tenkan > Kijun, price above cloud, Chikou confirmation, avoid doji, and a
    # valid Stage3 confirmation trigger (retest or clean Tenkan-cross confirmation).
    ichimoku_score = (
        _bool_score(g["tenkan_above_kijun"], 5)
        + _bool_score(g["above_cloud"], 5)
        + _bool_score(g["chikou_bullish"], 5)
        + _bool_score(~g["doji_risk"].fillna(True).astype(bool), 3)
        + _bool_score(stage >= 3, 7)
    )
    ichimoku_score = np.minimum(np.asarray(ichimoku_score, dtype=float), 25.0)

    lecture_score = np.asarray(rsi_score, dtype=float) + macd_score + ichimoku_score
    lecture_score = np.clip(lecture_score, 0.0, 60.0)

    # ------------------------------------------------------------------
    # Quality Enhancement: 40
    # These are explicitly secondary. They rank lecture signals; they do not define
    # the lecture signal itself.
    # ------------------------------------------------------------------
    # Trend 10: favor intact medium/long trend without requiring price > MA20,
    # because a good RSI Stage1 can occur during a temporary pullback below MA20.
    trend_score = (
        _bool_score(g["close_vs_ma60"] > 0, 3)
        + _bool_score(g["close_vs_ma120"] > 0, 2)
        + _bool_score(g["ma20_above_ma60"], 2)
        + _bool_score(g["ma60_slope"] > 0, 3)
    )

    # Relative Strength 10: emphasize 60-day strength, while allowing a short-term
    # relative pullback that may be creating the RSI setup.
    rs20 = pd.to_numeric(g["rs_20"], errors="coerce")
    rs60 = pd.to_numeric(g["rs_60"], errors="coerce")
    p20 = pd.to_numeric(g["rs_percentile_20"], errors="coerce")
    p60 = pd.to_numeric(g["rs_percentile_60"], errors="coerce")
    rs_score = (
        _tier_score(p60, [(0.80, 4.0), (0.60, 3.0), (0.40, 1.5)])
        + np.where(rs60.isna(), 1.0, np.where(rs60 > 0, 3.0, 0.0))
        + _tier_score(p20, [(0.70, 2.0), (0.50, 1.0)])
        + np.where(rs20.isna(), 0.5, np.where(rs20 > -0.03, 1.0, 0.0))
    )
    rs_score = np.minimum(np.asarray(rs_score, dtype=float), 10.0)

    # Volume 5: stage-aware. Stage1 prefers contraction during pullback; Stage2/3
    # prefer renewed participation/expansion as confirmation develops.
    stage1_volume = (
        _bool_score(g["volume_contraction_10d"] <= 0.95, 3)
        + _bool_score(g["volume_ratio_20"] <= 1.10, 1)
        + _bool_score(g["volume_ratio_5"] >= 0.90, 1)
    )
    later_volume = (
        _bool_score(g["breakout_volume_ratio"] >= 1.20, 3)
        + _bool_score(g["volume_ratio_5"] >= 1.00, 2)
    )
    volume_score = np.where(stage.eq(1), np.asarray(stage1_volume), np.asarray(later_volume))
    volume_score = np.minimum(volume_score.astype(float), 5.0)

    # Price Structure 5: prefer a controlled pullback near the prior trend rather
    # than either no pullback (chasing) or a deep trend breakdown.
    pullback = pd.to_numeric(g["pullback_depth"], errors="coerce")
    distance60 = pd.to_numeric(g["distance_60d_high"], errors="coerce")
    close_atr = pd.to_numeric(g["close_vs_atr"], errors="coerce")
    pullback_points = np.select(
        [pullback.between(0.03, 0.12), pullback.between(0.12, 0.20), pullback.between(0.0, 0.03)],
        [3.0, 1.5, 1.0],
        default=0.0,
    )
    price_structure_score = (
        pullback_points
        + np.where(distance60.ge(-0.20).fillna(False), 1.0, 0.0)
        + np.where(close_atr.abs().le(2.0).fillna(False), 1.0, 0.0)
    )
    price_structure_score = np.minimum(price_structure_score.astype(float), 5.0)

    # Market 5: soft context only; never hard-block an otherwise valid lecture LONG.
    market_raw = pd.to_numeric(g["market_score"], errors="coerce")
    market_score = np.where(market_raw.isna(), 2.5, np.clip(market_raw, 0, 5))

    # Risk/Chase 5: stop geometry and chasing are supporting risk controls.
    stop_distance = pd.to_numeric(g["stop_distance_pct"], errors="coerce")
    stop_score = np.select(
        [
            stop_distance.le(0.06),
            stop_distance.le(0.09),
            stop_distance.le(0.12),
            stop_distance.le(0.15),
        ],
        [3.0, 2.5, 2.0, 1.0],
        default=0.0,
    )
    stop_score = np.where(stop_distance.isna(), 1.5, stop_score)
    chase_points = np.select(
        [g["chase_risk"].eq("HIGH"), g["chase_risk"].eq("MEDIUM")],
        [0.0, 1.0],
        default=2.0,
    )
    risk_score = np.minimum(stop_score.astype(float) + chase_points.astype(float), 5.0)

    quality_score = (
        np.asarray(trend_score, dtype=float)
        + rs_score
        + volume_score
        + price_structure_score
        + np.asarray(market_score, dtype=float)
        + risk_score
    )
    quality_score = np.clip(quality_score, 0.0, 40.0)

    total = np.clip(lecture_score + quality_score, 0.0, 100.0)

    values = {
        "lecture_rsi_score": np.asarray(rsi_score, dtype=float),
        "lecture_macd_score": macd_score,
        "lecture_ichimoku_score": ichimoku_score,
        "lecture_score": lecture_score,
        "quality_trend_score": np.asarray(trend_score, dtype=float),
        "quality_rs_score": rs_score,
        "quality_volume_score": volume_score,
        "quality_price_structure_score": price_structure_score,
        "quality_market_score": np.asarray(market_score, dtype=float),
        "quality_risk_score": risk_score,
        "quality_enhancement_score": quality_score,
        "long_quality_score": total,
    }
    for col, arr in values.items():
        out.loc[g.index, col] = np.round(arr, 2)

    labels = np.select(
        [total >= confirmed_score, total >= watch_score],
        ["CONFIRMED", "WATCH"],
        default="REJECT",
    )
    out.loc[g.index, "long_quality_label"] = labels

    ranked = out.loc[mask].sort_values(
        ["signal_date", "long_quality_score", "lecture_score", "source_rank"],
        ascending=[True, False, False, True],
        kind="stable",
    )
    ranks = ranked.groupby("signal_date").cumcount() + 1
    out.loc[ranked.index, "daily_long_rank"] = ranks.astype("Int64").to_numpy()
    return out
