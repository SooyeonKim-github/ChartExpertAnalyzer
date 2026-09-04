from __future__ import annotations

import math

import pandas as pd

from ..models import BreakoutQualityResult


def _safe_float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(out) else out


def _ratio_score(value: float | None, steps: list[tuple[float, float]], default: float = 0.0) -> float:
    if value is None:
        return default
    for threshold, score in steps:
        if value >= threshold:
            return score
    return default


def _distance_score(distance_pct: float | None) -> float:
    if distance_pct is None or distance_pct < 0:
        return 0.0
    if distance_pct < 0.5:
        return 5.0
    if distance_pct < 1.5:
        return 10.0
    if distance_pct <= 4.0:
        return 15.0
    if distance_pct <= 7.0:
        return 11.0
    if distance_pct <= 10.0:
        return 6.0
    return 2.0


def _clv_score(clv: float | None) -> float:
    if clv is None:
        return 0.0
    return _ratio_score(clv, [(0.90, 20.0), (0.80, 18.0), (0.70, 15.0), (0.60, 10.0), (0.50, 5.0)])


def _wick_score(upper_wick_ratio: float | None) -> float:
    if upper_wick_ratio is None:
        return 0.0
    if upper_wick_ratio <= 0.10:
        return 15.0
    if upper_wick_ratio <= 0.20:
        return 12.0
    if upper_wick_ratio <= 0.30:
        return 8.0
    if upper_wick_ratio <= 0.40:
        return 4.0
    return 0.0


def _turnover_score(ratio: float | None) -> float:
    return _ratio_score(ratio, [(3.0, 15.0), (2.0, 13.0), (1.5, 10.0), (1.2, 7.0), (1.0, 4.0)])


def _volume_score(ratio: float | None) -> float:
    return _ratio_score(ratio, [(2.0, 5.0), (1.5, 4.0), (1.2, 3.0), (1.0, 1.0)])


def _gap_score(gap_pct: float | None) -> float:
    if gap_pct is None:
        return 0.0
    if -1.0 <= gap_pct <= 2.0:
        return 5.0
    if -3.0 <= gap_pct < -1.0:
        return 3.0
    if 2.0 < gap_pct <= 4.0:
        return 4.0
    if 4.0 < gap_pct <= 6.0:
        return 2.0
    if 6.0 < gap_pct <= 10.0:
        return 1.0
    return 0.0


def _prebreakout_structure(daily: pd.DataFrame, breakout_reference: float) -> tuple[float, float | None, float | None]:
    if len(daily) < 22:
        return 0.0, None, None

    prev_close = _safe_float(daily.iloc[-2]["close"])
    pre_distance = None
    near_score = 0.0
    if prev_close is not None and breakout_reference > 0:
        pre_distance = (prev_close / breakout_reference - 1.0) * 100.0
        if -2.0 <= pre_distance <= 0.5:
            near_score = 6.0
        elif -4.0 <= pre_distance < -2.0:
            near_score = 4.0
        elif -7.0 <= pre_distance < -4.0:
            near_score = 2.0

    prior = daily.iloc[:-1].copy()
    high = pd.to_numeric(prior["high"], errors="coerce")
    low = pd.to_numeric(prior["low"], errors="coerce")
    close = pd.to_numeric(prior["close"], errors="coerce")
    prev = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    atr5 = tr.tail(5).mean()
    atr20 = tr.tail(20).mean()
    contraction = None
    contraction_score = 0.0
    if pd.notna(atr5) and pd.notna(atr20) and float(atr20) > 0:
        contraction = float(atr5) / float(atr20)
        if contraction <= 0.70:
            contraction_score = 4.0
        elif contraction <= 0.85:
            contraction_score = 3.0
        elif contraction <= 1.00:
            contraction_score = 1.5

    return near_score + contraction_score, pre_distance, contraction


def score_breakout_quality(
    daily: pd.DataFrame,
    breakout_reference: float | None,
    breakout_type: str | None,
    cfg: dict,
) -> BreakoutQualityResult:
    qcfg = cfg.get("breakout_quality", {})
    if not qcfg.get("enabled", True):
        return BreakoutQualityResult(None, "DISABLED", False, breakout_type, breakout_reference)
    if daily is None or len(daily) < 21 or breakout_reference is None or breakout_reference <= 0 or not breakout_type:
        return BreakoutQualityResult(None, "NO_BREAKOUT", False, breakout_type, breakout_reference)

    cur = daily.iloc[-1]
    prev = daily.iloc[-2]
    open_ = _safe_float(cur.get("open"))
    high = _safe_float(cur.get("high"))
    low = _safe_float(cur.get("low"))
    close = _safe_float(cur.get("close"))
    prev_close = _safe_float(prev.get("close"))
    volume = _safe_float(cur.get("volume")) or 0.0
    trading_value = _safe_float(cur.get("trading_value")) or 0.0
    if None in (open_, high, low, close) or high <= low:
        return BreakoutQualityResult(None, "INVALID", False, breakout_type, breakout_reference)

    candle_range = high - low
    clv = max(0.0, min(1.0, (close - low) / candle_range))
    upper_wick = max(0.0, high - max(open_, close))
    upper_wick_ratio = upper_wick / candle_range
    breakout_distance_pct = (close / breakout_reference - 1.0) * 100.0
    breakout_hold_pct = breakout_distance_pct
    gap_pct = None if prev_close is None or prev_close <= 0 else (open_ / prev_close - 1.0) * 100.0

    prior20 = daily.iloc[-21:-1]
    avg_volume20 = pd.to_numeric(prior20["volume"], errors="coerce").mean()
    avg_turnover20 = pd.to_numeric(prior20["trading_value"], errors="coerce").mean() if "trading_value" in prior20.columns else None
    volume_ratio20 = None if pd.isna(avg_volume20) or float(avg_volume20) <= 0 else volume / float(avg_volume20)
    turnover_ratio20 = None if avg_turnover20 is None or pd.isna(avg_turnover20) or float(avg_turnover20) <= 0 else trading_value / float(avg_turnover20)

    structure_score, pre_distance, contraction = _prebreakout_structure(daily, breakout_reference)

    hold_score = 0.0
    if low >= breakout_reference:
        hold_score = 15.0
    elif close >= breakout_reference:
        hold_score = 12.0
    elif close >= breakout_reference * 0.995:
        hold_score = 7.0

    score = (
        _distance_score(breakout_distance_pct)
        + _clv_score(clv)
        + _wick_score(upper_wick_ratio)
        + _turnover_score(turnover_ratio20)
        + _volume_score(volume_ratio20)
        + hold_score
        + _gap_score(gap_pct)
        + structure_score
    )
    score = round(max(0.0, min(100.0, score)), 2)

    thresholds = qcfg.get("thresholds", {})
    clean_min = float(thresholds.get("clean", 85.0))
    valid_min = float(thresholds.get("valid", 70.0))
    weak_min = float(thresholds.get("weak", 50.0))
    failed_wick = float(thresholds.get("failed_upper_wick_ratio", 0.55))
    failed_gap = float(thresholds.get("failed_gap_pct", 12.0))
    excessive_gap = float(thresholds.get("excessive_gap_pct", 8.0))

    false_breakout = bool(high > breakout_reference and close < breakout_reference)
    exhaustion_risk = bool(
        (turnover_ratio20 is not None and turnover_ratio20 >= 6.0 and upper_wick_ratio >= 0.35)
        or (gap_pct is not None and gap_pct >= excessive_gap and clv < 0.60)
        or breakout_distance_pct >= 10.0
    )

    if false_breakout or (gap_pct is not None and gap_pct >= failed_gap and clv < 0.60):
        label = "FAILED_BREAKOUT"
    elif score >= clean_min:
        label = "CLEAN_BREAKOUT"
    elif score >= valid_min:
        label = "VALID_BREAKOUT"
    elif score >= weak_min:
        label = "WEAK_BREAKOUT"
    else:
        label = "FAILED_BREAKOUT"

    if upper_wick_ratio >= failed_wick and label in {"CLEAN_BREAKOUT", "VALID_BREAKOUT"}:
        label = "WEAK_BREAKOUT"
    if exhaustion_risk and label == "CLEAN_BREAKOUT":
        label = "VALID_BREAKOUT"

    return BreakoutQualityResult(
        score=score,
        label=label,
        available=True,
        breakout_type=breakout_type,
        breakout_reference=round(float(breakout_reference), 4),
        breakout_distance_pct=round(breakout_distance_pct, 3),
        close_location_value=round(clv, 4),
        upper_wick_ratio=round(upper_wick_ratio, 4),
        volume_ratio_20=None if volume_ratio20 is None else round(volume_ratio20, 3),
        turnover_ratio_20=None if turnover_ratio20 is None else round(turnover_ratio20, 3),
        gap_pct=None if gap_pct is None else round(gap_pct, 3),
        breakout_hold_pct=round(breakout_hold_pct, 3),
        pre_breakout_distance_pct=None if pre_distance is None else round(pre_distance, 3),
        volatility_contraction_ratio=None if contraction is None else round(contraction, 3),
        false_breakout=false_breakout,
        exhaustion_risk=exhaustion_risk,
        details={
            "distance_score": _distance_score(breakout_distance_pct),
            "close_location_score": _clv_score(clv),
            "upper_wick_score": _wick_score(upper_wick_ratio),
            "turnover_score": _turnover_score(turnover_ratio20),
            "volume_score": _volume_score(volume_ratio20),
            "hold_score": hold_score,
            "gap_score": _gap_score(gap_pct),
            "structure_score": structure_score,
        },
    )
