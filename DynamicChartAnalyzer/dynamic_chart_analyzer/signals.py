from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyConfig


def crossed_up(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a.shift(1) <= b.shift(1)) & (a > b)


def crossed_down(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a.shift(1) >= b.shift(1)) & (a < b)


def _pivot_flags(series: pd.Series, window: int, kind: str) -> pd.Series:
    span = 2 * window + 1
    roll = series.rolling(span, center=True)
    if kind == "low":
        flags = series.eq(roll.min())
    else:
        flags = series.eq(roll.max())
    # A centered pivot technically needs future bars to become known. Shift the
    # detected flag by `window` so it only becomes available when confirmation bars
    # have actually elapsed. This preserves backtest causality.
    return flags.shift(window).astype("boolean").fillna(False).astype(bool)


def _confirmed_divergence(df: pd.DataFrame, cfg: StrategyConfig) -> tuple[pd.Series, pd.Series]:
    """Detect confirmed two-pivot RSI divergence without using future information.

    Bullish: newer confirmed price pivot is lower/equal while RSI pivot is higher.
    Bearish: newer confirmed price pivot is higher/equal while RSI pivot is lower.
    The lecture defines the geometry but not exact pivot math, so window/tolerance are
    explicit configuration choices.
    """
    n = len(df)
    bull = np.zeros(n, dtype=bool)
    bear = np.zeros(n, dtype=bool)

    low_flags = _pivot_flags(df["low"], cfg.divergence_pivot_window, "low").to_numpy()
    high_flags = _pivot_flags(df["high"], cfg.divergence_pivot_window, "high").to_numpy()
    low_indices: list[int] = []
    high_indices: list[int] = []

    for i in range(n):
        if low_flags[i]:
            # Because the flag was shifted for confirmation, the actual pivot bar is
            # `i - window`.
            p = i - cfg.divergence_pivot_window
            low_indices.append(p)
            low_indices = [x for x in low_indices if p - x <= cfg.divergence_lookback]
            if len(low_indices) >= 2:
                a, b = low_indices[-2], low_indices[-1]
                pa, pb = float(df["low"].iloc[a]), float(df["low"].iloc[b])
                ra, rb = float(df["rsi"].iloc[a]), float(df["rsi"].iloc[b])
                if np.isfinite([pa, pb, ra, rb]).all():
                    price_lower = pb <= pa * (1 + cfg.divergence_price_tolerance)
                    rsi_higher = rb >= ra + cfg.divergence_min_rsi_delta
                    bull[i] = price_lower and rsi_higher

        if high_flags[i]:
            p = i - cfg.divergence_pivot_window
            high_indices.append(p)
            high_indices = [x for x in high_indices if p - x <= cfg.divergence_lookback]
            if len(high_indices) >= 2:
                a, b = high_indices[-2], high_indices[-1]
                pa, pb = float(df["high"].iloc[a]), float(df["high"].iloc[b])
                ra, rb = float(df["rsi"].iloc[a]), float(df["rsi"].iloc[b])
                if np.isfinite([pa, pb, ra, rb]).all():
                    price_higher = pb >= pa * (1 - cfg.divergence_price_tolerance)
                    rsi_lower = rb <= ra - cfg.divergence_min_rsi_delta
                    bear[i] = price_higher and rsi_lower

    return pd.Series(bull, index=df.index), pd.Series(bear, index=df.index)


def _recent_true(series: pd.Series, lookback: int) -> pd.Series:
    return series.astype(int).rolling(lookback, min_periods=1).max().astype(bool)


def add_signals(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()

    # Stage 1: leave the extreme zone. The lecture explicitly warns against buying
    # merely because RSI touched 30 (or shorting just because it touched 70).
    out["long_stage1"] = (out["rsi"].shift(1) <= cfg.rsi_oversold) & (out["rsi"] > cfg.rsi_oversold)
    out["short_stage1"] = (out["rsi"].shift(1) >= cfg.rsi_overbought) & (out["rsi"] < cfg.rsi_overbought)

    bullish_div, bearish_div = _confirmed_divergence(out, cfg)
    out["bullish_divergence"] = bullish_div
    out["bearish_divergence"] = bearish_div
    # Divergence is a confidence enhancer, not a mandatory Stage-1 gate in the staged
    # example. Preserve a recent-memory flag for reporting/confirmation.
    out["bullish_divergence_recent"] = _recent_true(bullish_div, cfg.divergence_lookback)
    out["bearish_divergence_recent"] = _recent_true(bearish_div, cfg.divergence_lookback)

    # MACD confirmation. A golden cross below zero is the lecture's preferred long
    # location; histogram direction is exposed explicitly rather than silently ignored.
    out["macd_golden"] = crossed_up(out["macd"], out["macd_signal"])
    out["macd_dead"] = crossed_down(out["macd"], out["macd_signal"])
    out["macd_golden_below_zero"] = out["macd_golden"] & (out["macd"] < 0)
    out["macd_dead_above_zero"] = out["macd_dead"] & (out["macd"] > 0)
    out["macd_hist_rising"] = out["macd_hist"] > out["macd_hist"].shift(1)
    out["macd_hist_falling"] = out["macd_hist"] < out["macd_hist"].shift(1)
    out["macd_hist_turn_positive"] = (out["macd_hist"].shift(1) <= 0) & (out["macd_hist"] > 0)
    out["macd_hist_turn_negative"] = (out["macd_hist"].shift(1) >= 0) & (out["macd_hist"] < 0)

    out["long_stage2"] = (
        out["macd_golden_below_zero"]
        & out["macd_hist_rising"]
        & (out["rsi"] > cfg.rsi_oversold)
    )
    out["short_stage2"] = (
        out["macd_dead"]
        & out["macd_hist_falling"]
        & (out["rsi"] < cfg.rsi_overbought)
    )

    # Candle quality.
    candle_range = (out["high"] - out["low"]).replace(0, np.nan)
    body_abs = (out["close"] - out["open"]).abs()
    body_signed = out["close"] - out["open"]
    out["doji_risk"] = (body_abs / candle_range) <= cfg.doji_body_ratio_max
    out["bullish_candle"] = body_signed > 0
    out["bearish_candle"] = body_signed < 0
    out["strong_bullish_candle"] = out["bullish_candle"] & (body_abs >= out["atr"] * cfg.strong_candle_body_atr_min)
    out["strong_bearish_candle"] = out["bearish_candle"] & (body_abs >= out["atr"] * cfg.strong_candle_body_atr_min)
    out["bullish_engulfing"] = (
        out["bullish_candle"]
        & (out["close"].shift(1) < out["open"].shift(1))
        & (out["open"] <= out["close"].shift(1))
        & (out["close"] >= out["open"].shift(1))
    )
    out["bearish_engulfing"] = (
        out["bearish_candle"]
        & (out["close"].shift(1) > out["open"].shift(1))
        & (out["open"] >= out["close"].shift(1))
        & (out["close"] <= out["open"].shift(1))
    )

    # The lecture also presents a compact non-staged trigger example:
    # divergence -> MACD cross -> engulfing/strong confirmation candle.
    out["classic_long_trigger"] = (
        out["bullish_divergence_recent"]
        & out["macd_golden"]
        & (out["bullish_engulfing"] | out["strong_bullish_candle"])
    )
    out["classic_short_trigger"] = (
        out["bearish_divergence_recent"]
        & out["macd_dead"]
        & (out["bearish_engulfing"] | out["strong_bearish_candle"])
    )

    # Ichimoku trend state.
    out["tenkan_cross_up"] = crossed_up(out["tenkan"], out["kijun"])
    out["tenkan_cross_down"] = crossed_down(out["tenkan"], out["kijun"])
    out["above_cloud"] = out["close"] > out["cloud_top"]
    out["below_cloud"] = out["close"] < out["cloud_bottom"]
    out["cloud_breakout"] = (out["close"].shift(1) <= out["cloud_top"].shift(1)) & out["above_cloud"]
    out["cloud_breakdown"] = (out["close"].shift(1) >= out["cloud_bottom"].shift(1)) & out["below_cloud"]
    out["thick_cloud"] = out["cloud_width_atr"] >= cfg.thick_cloud_atr_ratio

    recent_breakout = _recent_true(out["cloud_breakout"].shift(1).astype("boolean").fillna(False).astype(bool), cfg.cloud_retest_lookback)
    out["cloud_retest_hold"] = (
        recent_breakout
        & (out["low"] <= out["cloud_top"] * (1 + cfg.cloud_retest_tolerance))
        & (out["close"] >= out["cloud_top"])
        & out["bullish_candle"]
    )

    recent_breakdown = _recent_true(out["cloud_breakdown"].shift(1).astype("boolean").fillna(False).astype(bool), cfg.cloud_retest_lookback)
    out["cloud_retest_reject"] = (
        recent_breakdown
        & (out["high"] >= out["cloud_bottom"] * (1 - cfg.cloud_retest_tolerance))
        & (out["close"] <= out["cloud_bottom"])
        & out["bearish_candle"]
    )

    # Chikou confirmation proxy without look-ahead: current close vs close 26 bars ago.
    out["chikou_bullish"] = out["close"] > out["chikou_reference_price"]
    out["chikou_bearish"] = out["close"] < out["chikou_reference_price"]

    # Stage 3 = broad Ichimoku agreement.  Retest is preferred, but a fresh Tenkan
    # cross plus a strong candle can also confirm a clean breakout. Doji bars are rejected.
    out["long_stage3"] = (
        (out["tenkan"] > out["kijun"])
        & out["above_cloud"]
        & out["chikou_bullish"]
        & (~out["doji_risk"])
        & (
            out["cloud_retest_hold"]
            | (out["tenkan_cross_up"] & (out["strong_bullish_candle"] | out["bullish_engulfing"]))
        )
    )
    out["short_stage3"] = (
        (out["tenkan"] < out["kijun"])
        & out["below_cloud"]
        & out["chikou_bearish"]
        & (~out["doji_risk"])
        & (
            out["cloud_retest_reject"]
            | (out["tenkan_cross_down"] & (out["strong_bearish_candle"] | out["bearish_engulfing"]))
        )
    )

    # Main staged exits from the lecture.
    out["long_exit1"] = out["macd_dead"]
    out["long_exit2"] = (out["rsi"].shift(1) >= cfg.rsi_trend_midline) & (out["rsi"] < cfg.rsi_trend_midline)
    out["long_exit3"] = out["cloud_breakdown"]
    out["short_exit1"] = out["macd_golden"]
    out["short_exit2"] = (out["rsi"].shift(1) <= cfg.rsi_trend_midline) & (out["rsi"] > cfg.rsi_trend_midline)
    out["short_exit3"] = out["cloud_breakout"]

    # A compact explanation column is useful when reviewing candidate CSVs manually.
    out["long_confirmation_count"] = (
        out[["long_stage1", "bullish_divergence_recent", "long_stage2", "long_stage3"]]
        .astype(int)
        .sum(axis=1)
    )
    out["short_confirmation_count"] = (
        out[["short_stage1", "bearish_divergence_recent", "short_stage2", "short_stage3"]]
        .astype(int)
        .sum(axis=1)
    )
    return out
