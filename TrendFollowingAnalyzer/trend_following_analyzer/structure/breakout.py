from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
BREAKOUT_WEAK_VOLUME = "BREAKOUT_WEAK_VOLUME"
INTRADAY_REJECTED = "INTRADAY_REJECTED"
NEAR_BREAKOUT = "NEAR_BREAKOUT"
NOT_BREAKOUT = "NOT_BREAKOUT"
NO_BASE = "NO_BASE"
INSUFFICIENT = "INSUFFICIENT"
MEASUREMENT = "BASE_BREAKOUT_V1"


@dataclass(frozen=True)
class BreakoutSnapshot:
    status: str
    measurement: str
    base_start_date: str | None
    base_end_date: str | None
    breakout_date: str | None
    breakout_level: float | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    close_breakout_pct: float | None
    intraday_high_breakout_pct: float | None
    gap_pct: float | None
    close_location_value: float | None
    breakout_volume: float | None
    reference_volume_avg: float | None
    breakout_volume_ratio: float | None
    experimental_price_pass: bool
    experimental_volume_pass: bool
    experimental_signal_pass: bool
    experimental_false_breakout: bool
    filter_applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _empty(status: str, base_start_date: str | None = None) -> BreakoutSnapshot:
    return BreakoutSnapshot(
        status=status,
        measurement=MEASUREMENT,
        base_start_date=base_start_date,
        base_end_date=None,
        breakout_date=None,
        breakout_level=None,
        open=None,
        high=None,
        low=None,
        close=None,
        close_breakout_pct=None,
        intraday_high_breakout_pct=None,
        gap_pct=None,
        close_location_value=None,
        breakout_volume=None,
        reference_volume_avg=None,
        breakout_volume_ratio=None,
        experimental_price_pass=False,
        experimental_volume_pass=False,
        experimental_signal_pass=False,
        experimental_false_breakout=False,
        filter_applied=False,
    )


def compute_breakout_snapshot(
    df: pd.DataFrame,
    *,
    pre_base_status: str,
    pre_base_start_date: str | None,
    as_of=None,
    experimental_min_close_breakout_pct: float = 0.0,
    experimental_min_volume_ratio: float = 1.50,
    experimental_near_breakout_pct: float = 3.0,
    reference_volume_sessions: int = 20,
) -> BreakoutSnapshot:
    """Evaluate the current session against a base detected through the prior session."""
    if str(pre_base_status) != "BASE_DETECTED" or not pre_base_start_date:
        return _empty(NO_BASE, pre_base_start_date)
    required = {"open", "high", "low", "close", "volume"}
    if df is None or df.empty or not required.issubset(df.columns):
        return _empty(INSUFFICIENT, pre_base_start_date)

    frame = df[list(required)].copy()
    for col in required:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame = frame[~frame.index.isna()].sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    if as_of is not None:
        frame = frame[frame.index.normalize() <= pd.Timestamp(as_of).normalize()]
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    if len(frame) < 2:
        return _empty(INSUFFICIENT, pre_base_start_date)

    current = frame.iloc[-1]
    current_date = pd.Timestamp(frame.index[-1]).normalize()
    start = pd.Timestamp(pre_base_start_date).normalize()
    prior = frame[(frame.index.normalize() >= start) & (frame.index.normalize() < current_date)]
    if prior.empty:
        return _empty(INSUFFICIENT, pre_base_start_date)

    level = float(prior["high"].max())
    if level <= 0:
        return _empty(INSUFFICIENT, pre_base_start_date)
    open_ = float(current["open"])
    high = float(current["high"])
    low = float(current["low"])
    close = float(current["close"])
    volume = float(current["volume"])
    prev_close = float(prior["close"].iloc[-1])

    close_breakout_pct = (close / level - 1.0) * 100.0
    high_breakout_pct = (high / level - 1.0) * 100.0
    gap_pct = (open_ / prev_close - 1.0) * 100.0 if prev_close > 0 else None
    clv = None if high <= low else float((close - low) / (high - low))

    ref = pd.to_numeric(prior["volume"].iloc[-int(reference_volume_sessions):], errors="coerce").dropna()
    ref = ref[ref >= 0]
    ref_avg = None if ref.empty else float(ref.mean())
    volume_ratio = None if ref_avg is None or ref_avg <= 0 else float(volume / ref_avg)

    price_pass = bool(close_breakout_pct >= float(experimental_min_close_breakout_pct))
    volume_pass = bool(volume_ratio is not None and volume_ratio >= float(experimental_min_volume_ratio))
    false_breakout = bool(high >= level and close < level)

    if price_pass and volume_pass:
        status = BREAKOUT_CONFIRMED
    elif price_pass:
        status = BREAKOUT_WEAK_VOLUME
    elif false_breakout:
        status = INTRADAY_REJECTED
    elif close_breakout_pct >= -float(experimental_near_breakout_pct):
        status = NEAR_BREAKOUT
    else:
        status = NOT_BREAKOUT

    return BreakoutSnapshot(
        status=status,
        measurement=MEASUREMENT,
        base_start_date=pd.Timestamp(prior.index[0]).strftime("%Y-%m-%d"),
        base_end_date=pd.Timestamp(prior.index[-1]).strftime("%Y-%m-%d"),
        breakout_date=current_date.strftime("%Y-%m-%d"),
        breakout_level=level,
        open=open_,
        high=high,
        low=low,
        close=close,
        close_breakout_pct=close_breakout_pct,
        intraday_high_breakout_pct=high_breakout_pct,
        gap_pct=gap_pct,
        close_location_value=clv,
        breakout_volume=volume,
        reference_volume_avg=ref_avg,
        breakout_volume_ratio=volume_ratio,
        experimental_price_pass=price_pass,
        experimental_volume_pass=volume_pass,
        experimental_signal_pass=bool(price_pass and volume_pass),
        experimental_false_breakout=false_breakout,
        filter_applied=False,
    )
