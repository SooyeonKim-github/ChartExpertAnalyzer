from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyConfig


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-style RSI using exponentially smoothed gains/losses."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(avg_loss.ne(0), 100.0)
    out = out.where(avg_gain.ne(0), 0.0)
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    signal_line = line.ewm(span=signal, adjust=False).mean()
    hist = line - signal_line
    return pd.DataFrame(
        {"macd": line, "macd_signal": signal_line, "macd_hist": hist},
        index=close.index,
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def ichimoku(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tenkan = (
        high.rolling(cfg.ichimoku_tenkan).max()
        + low.rolling(cfg.ichimoku_tenkan).min()
    ) / 2.0
    kijun = (
        high.rolling(cfg.ichimoku_kijun).max()
        + low.rolling(cfg.ichimoku_kijun).min()
    ) / 2.0

    # Current-bar visible cloud. Raw spans are displaced +26 bars, so aligning the
    # displayed cloud back to today's bar requires a +26 shift of historical values.
    senkou_a_raw = (tenkan + kijun) / 2.0
    senkou_b_raw = (
        high.rolling(cfg.ichimoku_senkou_b).max()
        + low.rolling(cfg.ichimoku_senkou_b).min()
    ) / 2.0
    senkou_a = senkou_a_raw.shift(cfg.ichimoku_displacement)
    senkou_b = senkou_b_raw.shift(cfg.ichimoku_displacement)

    cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
    cloud_bottom = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
    chikou_reference_price = close.shift(cfg.ichimoku_displacement)

    return pd.DataFrame(
        {
            "tenkan": tenkan,
            "kijun": kijun,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b,
            "cloud_top": cloud_top,
            "cloud_bottom": cloud_bottom,
            "cloud_width": (cloud_top - cloud_bottom).abs(),
            "chikou_reference_price": chikou_reference_price,
        },
        index=df.index,
    )


def experimental_dynamic_rsi(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """Transparent approximation of the private Dynamic RSI from the lecture.

    The video describes a recent-data-weighted RSI plus adaptive overbought/oversold
    bands, but it does not disclose the proprietary formula.  This function is kept
    strictly experimental and is NOT used by the default entry logic.
    """
    base = rsi(df["close"], cfg.rsi_period)
    weighted = base.ewm(span=4, adjust=False).mean()
    center = weighted.rolling(20).mean()
    dispersion = weighted.rolling(20).std()
    upper = (center + 1.25 * dispersion).clip(lower=55, upper=90)
    lower = (center - 1.25 * dispersion).clip(lower=10, upper=45)
    return pd.DataFrame(
        {
            "dynamic_rsi": weighted,
            "dynamic_center": center,
            "dynamic_upper": upper,
            "dynamic_lower": lower,
        },
        index=df.index,
    )


def add_indicators(df: pd.DataFrame, cfg: StrategyConfig, include_dynamic_rsi: bool = False) -> pd.DataFrame:
    out = df.copy()
    out["rsi"] = rsi(out["close"], cfg.rsi_period)
    out["atr"] = atr(out, cfg.atr_period)
    out = out.join(macd(out["close"], cfg.macd_fast, cfg.macd_slow, cfg.macd_signal))
    out = out.join(ichimoku(out, cfg))
    out["cloud_width_atr"] = out["cloud_width"] / out["atr"].replace(0, np.nan)

    # Previous-swing invalidation levels. shift(1) prevents the current bar from
    # defining its own stop and keeps the rule free of look-ahead.
    out["long_stop_reference"] = out["low"].rolling(cfg.swing_stop_lookback).min().shift(1)
    out["short_stop_reference"] = out["high"].rolling(cfg.swing_stop_lookback).max().shift(1)

    if include_dynamic_rsi:
        out = out.join(experimental_dynamic_rsi(out, cfg))
        out["dynamic_long_exit"] = (
            (out["dynamic_rsi"].shift(1) <= out["dynamic_lower"].shift(1))
            & (out["dynamic_rsi"] > out["dynamic_lower"])
        )
        out["dynamic_short_exit"] = (
            (out["dynamic_rsi"].shift(1) >= out["dynamic_upper"].shift(1))
            & (out["dynamic_rsi"] < out["dynamic_upper"])
        )
    return out
