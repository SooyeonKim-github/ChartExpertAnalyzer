from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np
import pandas as pd

from config import StrategyConfig


@dataclass
class DailyScore:
    total_score: float
    price_structure_score: float
    trend_score: float
    candle_score: float
    volume_score: float
    heat_score: float
    risk_score: float

    close: float
    daily_return_pct: float
    signal_gain_pct: float
    volume_ratio_20: Optional[float]
    ma5: Optional[float]
    ma20: Optional[float]
    ma20_distance_pct: Optional[float]
    close_location: float
    range_ratio_10: Optional[float]
    hard_cancel_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_float(value, default=np.nan) -> float:
    try:
        value = float(value)
        return value if np.isfinite(value) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _volume_ratio(history: pd.DataFrame) -> float:
    if "Volume" not in history.columns or history.empty:
        return np.nan
    volume = pd.to_numeric(history["Volume"], errors="coerce")
    if volume.empty or pd.isna(volume.iloc[-1]):
        return np.nan
    base = volume.iloc[-20:].mean()
    if pd.isna(base) or base <= 0:
        return np.nan
    return float(volume.iloc[-1] / base)


def _range_ratio(history: pd.DataFrame) -> float:
    if history.empty:
        return np.nan
    close = pd.to_numeric(history["Close"], errors="coerce")
    high = pd.to_numeric(history["High"], errors="coerce")
    low = pd.to_numeric(history["Low"], errors="coerce")
    range_pct = (high - low) / close.replace(0, np.nan)
    if range_pct.empty or pd.isna(range_pct.iloc[-1]):
        return np.nan
    base = range_pct.iloc[-10:].mean()
    if pd.isna(base) or base <= 0:
        return np.nan
    return float(range_pct.iloc[-1] / base)


def score_daily_state(
    history: pd.DataFrame,
    signal_bar: pd.Series,
    structural_stop: float,
    signal_close: float,
    cfg: StrategyConfig,
) -> DailyScore:
    if history.empty:
        raise ValueError("history is empty")

    bar = history.iloc[-1]
    prev = history.iloc[-2] if len(history) >= 2 else bar

    close = _safe_float(bar["Close"])
    open_ = _safe_float(bar["Open"], close)
    high = _safe_float(bar["High"], close)
    low = _safe_float(bar["Low"], close)
    prev_close = _safe_float(prev["Close"], close)
    prev_high = _safe_float(prev["High"], high)

    ma5 = _safe_float(bar.get("MA5"))
    ma10 = _safe_float(bar.get("MA10"))
    ma20 = _safe_float(bar.get("MA20"))
    signal_low = _safe_float(signal_bar.get("Low"), signal_close)

    daily_ret = close / prev_close - 1.0 if prev_close > 0 else 0.0
    signal_gain = close / signal_close - 1.0 if signal_close > 0 else 0.0
    ma20_distance = close / ma20 - 1.0 if np.isfinite(ma20) and ma20 > 0 else np.nan
    volume_ratio = _volume_ratio(history)
    range_ratio = _range_ratio(history)

    day_range = max(high - low, 0.0)
    close_location = (close - low) / day_range if day_range > 0 else 0.5

    # V3 hard-cancel logic keeps only structural damage / distribution signals.
    # DAILY_CRASH and GAP_DOWN_FAILED_RECOVERY were removed because the range test
    # showed they could discard strong future performers.
    hard_cancel_reason = ""
    if np.isfinite(structural_stop) and close < structural_stop:
        hard_cancel_reason = "CLOSE_BELOW_STRUCTURAL_STOP"
    elif signal_low > 0 and close < signal_low:
        hard_cancel_reason = "CLOSE_BELOW_SIGNAL_LOW"
    elif (
        daily_ret <= -cfg.hard_cancel_distribution_drop_pct
        and np.isfinite(volume_ratio)
        and volume_ratio >= cfg.hard_cancel_volume_ratio
    ):
        hard_cancel_reason = "HIGH_VOLUME_DISTRIBUTION"

    # 1) Price structure: 25
    price_structure = 0.0
    if close >= signal_low:
        price_structure += 8.0
    if not np.isfinite(structural_stop) or close >= structural_stop:
        price_structure += 7.0
    if np.isfinite(ma20) and close >= ma20:
        price_structure += 5.0
    prior_lows = pd.to_numeric(history["Low"], errors="coerce").iloc[-6:-1].dropna()
    if prior_lows.empty or close >= float(prior_lows.min()):
        price_structure += 5.0

    # 2) Trend: 20
    trend = 0.0
    if np.isfinite(ma5) and close >= ma5:
        trend += 5.0
    if np.isfinite(ma5) and np.isfinite(ma10) and ma5 >= ma10:
        trend += 5.0
    if np.isfinite(ma10) and np.isfinite(ma20) and ma10 >= ma20:
        trend += 5.0
    if len(history) >= 6:
        ma20_old = _safe_float(history.iloc[-6].get("MA20"))
        if np.isfinite(ma20) and np.isfinite(ma20_old) and ma20 >= ma20_old:
            trend += 5.0
    elif np.isfinite(ma20):
        trend += 2.5

    # 3) Candle quality: 15
    candle = 0.0
    if close > open_:
        candle += 5.0
    if close_location >= 0.65:
        candle += 5.0
    elif close_location >= 0.50:
        candle += 2.5
    if close > prev_high:
        candle += 5.0

    # 4) Volume quality: 15
    if not np.isfinite(volume_ratio):
        volume = 7.5
    elif daily_ret > 0 and volume_ratio >= 1.10:
        volume = 15.0
    elif daily_ret > 0:
        volume = 10.0
    elif daily_ret <= 0 and volume_ratio <= 0.90:
        volume = 12.0
    elif daily_ret <= 0 and volume_ratio >= cfg.hard_cancel_volume_ratio:
        volume = 0.0
    else:
        volume = 6.0

    # 5) Heat / chase slot: 15
    # V3 no longer penalizes a stock simply because it already moved strongly.
    # Keep the slot at a neutral full score so the 100-point scale remains compatible.
    heat = 15.0

    # 6) Volatility / risk: 10. Higher is calmer.
    if not np.isfinite(range_ratio):
        risk = 5.0
    elif range_ratio <= 1.0:
        risk = 10.0
    elif range_ratio <= 1.5:
        risk = 7.0
    elif range_ratio <= 2.0:
        risk = 4.0
    else:
        risk = 0.0

    total = price_structure + trend + candle + volume + heat + risk
    return DailyScore(
        total_score=float(total),
        price_structure_score=float(price_structure),
        trend_score=float(trend),
        candle_score=float(candle),
        volume_score=float(volume),
        heat_score=float(heat),
        risk_score=float(risk),
        close=float(close),
        daily_return_pct=float(daily_ret * 100.0),
        signal_gain_pct=float(signal_gain * 100.0),
        volume_ratio_20=None if not np.isfinite(volume_ratio) else float(volume_ratio),
        ma5=None if not np.isfinite(ma5) else float(ma5),
        ma20=None if not np.isfinite(ma20) else float(ma20),
        ma20_distance_pct=None if not np.isfinite(ma20_distance) else float(ma20_distance * 100.0),
        close_location=float(close_location),
        range_ratio_10=None if not np.isfinite(range_ratio) else float(range_ratio),
        hard_cancel_reason=hard_cancel_reason,
    )
