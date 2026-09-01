from __future__ import annotations

import numpy as np
import pandas as pd

from config import PullbackConfig
from models import ImpulseContext, PullbackContext


def detect_pullback(d: pd.DataFrame, impulse: ImpulseContext, cfg: PullbackConfig) -> PullbackContext:
    if not impulse.available or impulse.bar_pos < 0 or impulse.bar_pos >= len(d) - 1:
        return PullbackContext()

    seg = d.iloc[impulse.bar_pos + 1 :]
    if seg.empty:
        return PullbackContext()

    low_values = seg["Low"].to_numpy(dtype=float)
    low_local = int(np.nanargmin(low_values))
    low_pos = impulse.bar_pos + 1 + low_local
    low_price = float(d["Low"].iloc[low_pos])
    current = float(d["Close"].iloc[-1])
    impulse_range = impulse.high_price - impulse.base_price
    retr = (impulse.high_price - low_price) / impulse_range if impulse_range > 0 else np.nan
    depth = (impulse.high_price / low_price - 1.0) * 100.0 if low_price > 0 else np.nan
    current_dd = (current / impulse.high_price - 1.0) * 100.0 if impulse.high_price > 0 else np.nan
    midpoint = impulse.base_price + impulse_range * 0.5
    midpoint_broken = low_price < midpoint

    pre_start = max(0, impulse.base_pos - 20)
    prior_swing_low = float(d["Low"].iloc[pre_start : impulse.base_pos + 1].min())
    higher_low = bool(low_price > prior_swing_low * 1.01)

    bars = len(d) - 1 - impulse.bar_pos
    period_correction = bool(
        bars >= cfg.period_correction_min_bars
        and np.isfinite(retr)
        and retr <= cfg.ideal_retracement_max
    )
    price_correction = bool(np.isfinite(retr) and retr > cfg.ideal_retracement_max)
    correction_type = "PERIOD" if period_correction else ("PRICE" if price_correction else "SHALLOW")

    recent = d.iloc[impulse.bar_pos + 1 :]
    pullback_vol = float(recent["Volume"].mean()) if not recent.empty else np.nan
    impulse_vol_window = d["Volume"].iloc[max(0, impulse.bar_pos-2):impulse.bar_pos+1]
    impulse_vol = float(impulse_vol_window.mean()) if not impulse_vol_window.empty else np.nan
    vol_ratio_impulse = pullback_vol / impulse_vol if impulse_vol and impulse_vol > 0 else np.nan
    vol_ratio20 = float(recent["Volume"].tail(min(len(recent), 5)).mean() / d["VMA20"].iloc[-1]) if pd.notna(d["VMA20"].iloc[-1]) and d["VMA20"].iloc[-1] > 0 else np.nan

    prior_atr = d["ATR"].iloc[max(0, impulse.bar_pos-5):impulse.bar_pos+1].mean()
    recent_atr = recent["ATR"].tail(min(len(recent), 5)).mean()
    atr_contraction = bool(pd.notna(prior_atr) and prior_atr > 0 and pd.notna(recent_atr) and recent_atr < prior_atr)

    prior_range = d["Range"].iloc[max(0, impulse.bar_pos-5):impulse.bar_pos+1].mean()
    recent_range = recent["Range"].tail(min(len(recent), 5)).mean()
    range_contraction = bool(pd.notna(prior_range) and prior_range > 0 and pd.notna(recent_range) and recent_range < prior_range)

    stop_n = min(cfg.price_stop_lookback_bars, len(d))
    lows = d["Low"].tail(stop_n).to_numpy(dtype=float)
    closes = d["Close"].tail(stop_n).to_numpy(dtype=float)
    price_stopping = False
    if len(lows) >= 3:
        price_stopping = bool(lows[-1] >= min(lows[:-1]) * 0.995 and closes[-1] >= min(closes[:-1]))

    recent5 = d.tail(min(5, len(d)))
    bearish = recent5["Close"] < recent5["Open"]
    high_volume = recent5["Volume_Ratio_20"] >= cfg.high_volume_breakdown_ratio
    long_body = recent5["Body_ATR"] >= cfg.long_bear_body_atr
    high_volume_breakdown = bool((bearish & high_volume & long_body).fillna(False).any())

    return PullbackContext(
        available=True, bars=bars, low_price=low_price, low_pos=low_pos, depth_pct=depth,
        retracement_ratio=float(retr) if np.isfinite(retr) else np.nan,
        current_drawdown_pct=current_dd, sequence=max(1, impulse.sequence),
        correction_type=correction_type, period_correction=period_correction,
        price_correction=price_correction, higher_low=higher_low,
        midpoint_broken=midpoint_broken, atr_contraction=atr_contraction,
        range_contraction=range_contraction, price_stopping=price_stopping,
        volume_ratio_impulse=vol_ratio_impulse, volume_ratio_20=vol_ratio20,
        high_volume_breakdown=high_volume_breakdown,
    )
