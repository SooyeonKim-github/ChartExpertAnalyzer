from __future__ import annotations

import numpy as np
import pandas as pd


BENCHMARK_PROXY = {
    "KOSPI": "069500",   # KODEX 200
    "KOSDAQ": "229200",  # KODEX KOSDAQ 150
}

BASE_EVENT_FEATURE_COLUMNS = [
    # RSI
    "rsi",
    "rsi_prev",
    "rsi_min_10d",
    "rsi_rebound_strength",
    # MACD
    "macd",
    "macd_signal",
    "macd_hist",
    "macd_hist_slope",
    "macd_distance_from_zero",
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
    # Ichimoku
    "cloud_distance",
    "cloud_thickness",
    "tenkan_kijun_gap",
    "cloud_retest",
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
    """Add LONG V2 research features without changing Stage1/2/3 signal logic.

    All rolling features use current/past bars only. Market features are aligned
    by trading date and are based on a liquid ETF proxy loaded through the same
    stable per-ticker OHLCV provider as stock data.
    """
    out = analyzed.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()

    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce")

    # RSI
    out["rsi_prev"] = out["rsi"].shift(1)
    out["rsi_min_10d"] = out["rsi"].rolling(10, min_periods=3).min()
    out["rsi_rebound_strength"] = out["rsi"] - out["rsi_min_10d"]

    # MACD
    out["macd_hist_slope"] = out["macd_hist"] - out["macd_hist"].shift(1)
    out["macd_distance_from_zero"] = _safe_ratio(out["macd"], close)

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

    # Volume. ratio baselines intentionally include only current/past data.
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
    out["rs_percentile_20"] = (
        out.groupby("signal_date")["rs_20"].rank(method="average", pct=True)
    )
    out["rs_percentile_60"] = (
        out.groupby("signal_date")["rs_60"].rank(method="average", pct=True)
    )
    return out


def _bool_score(series: pd.Series, points: float) -> pd.Series:
    return series.fillna(False).astype(bool).astype(float) * points


def score_long_events(
    events: pd.DataFrame,
    confirmed_score: float = 70.0,
    watch_score: float = 55.0,
) -> pd.DataFrame:
    """Score LONG entries while leaving existing Stage signals untouched."""
    out = events.copy()
    out["long_quality_score"] = np.nan
    out["long_quality_label"] = ""
    out["daily_long_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")

    mask = out["side"].eq("LONG")
    if not mask.any():
        return out

    g = out.loc[mask].copy()

    # Trend: 25
    trend = (
        _bool_score(g["close_vs_ma20"] > 0, 5)
        + _bool_score(g["close_vs_ma60"] > 0, 5)
        + _bool_score(g["ma20_above_ma60"], 5)
        + _bool_score(g["ma20_slope"] > 0, 5)
        + _bool_score(g["ma60_slope"] > 0, 5)
    )

    # Relative strength: 25. Missing market/percentile data receives neutral credit
    # rather than silently rejecting otherwise valid Stage signals.
    rs20 = pd.to_numeric(g["rs_20"], errors="coerce")
    rs60 = pd.to_numeric(g["rs_60"], errors="coerce")
    p20 = pd.to_numeric(g["rs_percentile_20"], errors="coerce")
    p60 = pd.to_numeric(g["rs_percentile_60"], errors="coerce")
    rs_score = (
        np.where(rs20.isna(), 4.0, np.where(rs20 > 0, 8.0, 0.0))
        + np.where(rs60.isna(), 4.0, np.where(rs60 > 0, 8.0, 0.0))
        + np.where(p20.isna(), 2.25, np.where(p20 >= 0.60, 4.5, 0.0))
        + np.where(p60.isna(), 2.25, np.where(p60 >= 0.60, 4.5, 0.0))
    )

    # Volume: 15
    volume_score = (
        _bool_score(g["volume_contraction_10d"] <= 0.95, 4)
        + _bool_score(g["volume_ratio_20"] >= 0.90, 3)
        + _bool_score(g["volume_ratio_5"] >= 1.00, 3)
        + _bool_score(g["breakout_volume_ratio"] >= 1.20, 5)
    )

    # Momentum/confirmation: 15
    momentum = (
        _bool_score(g["rsi_rebound_strength"] >= 5.0, 4)
        + _bool_score(g["macd_hist_slope"] > 0, 4)
        + _bool_score(g["macd_hist"] > 0, 3)
        + _bool_score(g["tenkan_kijun_gap"] > 0, 2)
        + _bool_score(g["cloud_retest"], 2)
    )

    # Market: 10
    market_score_raw = pd.to_numeric(g["market_score"], errors="coerce")
    market_score = np.where(
        market_score_raw.isna(),
        5.0,
        np.clip(market_score_raw, 0, 5) * 2.0,
    )

    # Chase: 10
    chase_score = np.select(
        [g["chase_risk"].eq("HIGH"), g["chase_risk"].eq("MEDIUM")],
        [0.0, 6.0],
        default=10.0,
    )

    total = np.asarray(trend, dtype=float) + np.asarray(rs_score, dtype=float)
    total += np.asarray(volume_score, dtype=float) + np.asarray(momentum, dtype=float)
    total += np.asarray(market_score, dtype=float) + np.asarray(chase_score, dtype=float)
    total = np.clip(total, 0.0, 100.0)

    out.loc[g.index, "long_quality_score"] = np.round(total, 2)
    labels = np.select(
        [total >= confirmed_score, total >= watch_score],
        ["CONFIRMED", "WATCH"],
        default="REJECT",
    )
    out.loc[g.index, "long_quality_label"] = labels

    ranked = out.loc[mask].sort_values(
        ["signal_date", "long_quality_score", "source_rank"],
        ascending=[True, False, True],
        kind="stable",
    )
    ranks = ranked.groupby("signal_date").cumcount() + 1
    out.loc[ranked.index, "daily_long_rank"] = ranks.astype("Int64").to_numpy()
    return out
