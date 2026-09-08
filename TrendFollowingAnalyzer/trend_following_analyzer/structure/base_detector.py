from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

BASE_DETECTED = "BASE_DETECTED"
TOO_DEEP = "TOO_DEEP"
TOO_FAR_FROM_HIGH = "TOO_FAR_FROM_HIGH"
TOO_LOOSE = "TOO_LOOSE"
NO_RESISTANCE_ANCHOR = "NO_RESISTANCE_ANCHOR"
NO_BASE = "NO_BASE"
INSUFFICIENT = "INSUFFICIENT"
MEASUREMENT = "GENERIC_PRICE_BASE_V1"
LINK_AVAILABLE = "AVAILABLE"


@dataclass(frozen=True)
class GenericBaseSnapshot:
    status: str
    measurement: str
    status_reason: str
    base_start_date: str | None
    base_end_date: str | None
    base_duration_sessions: int | None
    base_high_date: str | None
    base_high: float | None
    base_low_date: str | None
    base_low: float | None
    base_depth_pct: float | None
    current_vs_base_high_pct: float | None
    atr_early_pct: float | None
    atr_late_pct: float | None
    atr_contraction_ratio: float | None
    range_early_pct: float | None
    range_late_pct: float | None
    range_contraction_ratio: float | None
    close_dispersion_pct: float | None
    experimental_quality_score: float | None
    experimental_depth_pass: bool
    experimental_end_near_high_pass: bool
    experimental_resistance_pass: bool
    experimental_atr_contraction_pass: bool
    experimental_range_contraction_pass: bool
    filter_applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AdvanceBaseLinkSnapshot:
    status: str
    peak_to_base_sessions: int | None
    drawdown_from_prior_peak_to_base_low_pct: float | None
    advance_retention_ratio: float | None
    current_advance_retention_ratio: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_history(df: pd.DataFrame, *, as_of=None) -> pd.DataFrame:
    if df is None or df.empty or "close" not in df.columns:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    close = pd.to_numeric(df["close"], errors="coerce")
    out = pd.DataFrame(index=df.index)
    out["close"] = close
    out["open"] = pd.to_numeric(df["open"], errors="coerce") if "open" in df.columns else close
    out["high"] = pd.to_numeric(df["high"], errors="coerce") if "high" in df.columns else close
    out["low"] = pd.to_numeric(df["low"], errors="coerce") if "low" in df.columns else close
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    if as_of is not None:
        out = out[out.index.normalize() <= pd.Timestamp(as_of).normalize()]
    out = out.dropna(subset=["high", "low", "close"])
    out = out[(out["high"] > 0) & (out["low"] > 0) & (out["close"] > 0)]
    out["high"] = out[["high", "open", "close"]].max(axis=1)
    out["low"] = out[["low", "open", "close"]].min(axis=1)
    return out


def _true_range_pct(frame: pd.DataFrame) -> pd.Series:
    prev_close = frame["close"].shift(1)
    tr = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr / frame["close"].replace(0, np.nan) * 100.0


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or not np.isfinite(numerator) or not np.isfinite(denominator) or denominator <= 0:
        return None
    return float(numerator / denominator)


def _range_pct(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    high = float(frame["high"].max())
    low = float(frame["low"].min())
    return None if high <= 0 else (high - low) / high * 100.0


def _quality_score(depth_pct, current_vs_high_pct, atr_ratio, range_ratio, duration, max_depth_pct, max_end_drawdown_pct) -> float:
    depth_score = max(0.0, 1.0 - depth_pct / max(max_depth_pct, 1e-9))
    end_score = max(0.0, 1.0 - abs(min(current_vs_high_pct, 0.0)) / max(max_end_drawdown_pct, 1e-9))
    atr_score = 0.5 if atr_ratio is None else min(1.0, 1.0 / max(atr_ratio, 1e-9))
    range_score = 0.5 if range_ratio is None else min(1.0, 1.0 / max(range_ratio, 1e-9))
    duration_score = min(1.0, duration / 30.0)
    return float(100.0 * (0.25 * depth_score + 0.25 * end_score + 0.20 * atr_score + 0.20 * range_score + 0.10 * duration_score))


def _snapshot_from_window(window: pd.DataFrame, *, max_depth_pct: float, max_end_drawdown_pct: float, resistance_tolerance_pct: float) -> GenericBaseSnapshot:
    high_date = window["high"].idxmax()
    low_date = window["low"].idxmin()
    base_high = float(window.loc[high_date, "high"])
    base_low = float(window.loc[low_date, "low"])
    current = float(window["close"].iloc[-1])
    depth_pct = (1.0 - base_low / base_high) * 100.0
    current_vs_high_pct = (current / base_high - 1.0) * 100.0
    split = max(5, len(window) // 2)
    early = window.iloc[:split]
    late = window.iloc[split:]
    if late.empty:
        late = window.iloc[-split:]
    tr_pct = _true_range_pct(window)
    early_tr = tr_pct.iloc[:split].dropna()
    late_tr = tr_pct.iloc[split:].dropna()
    if late_tr.empty:
        late_tr = tr_pct.iloc[-split:].dropna()
    atr_early = float(early_tr.mean()) if not early_tr.empty else None
    atr_late = float(late_tr.mean()) if not late_tr.empty else None
    range_early = _range_pct(early)
    range_late = _range_pct(late)
    atr_ratio = _safe_ratio(atr_late, atr_early)
    range_ratio = _safe_ratio(range_late, range_early)
    close_mean = float(window["close"].mean())
    close_dispersion = float(window["close"].std(ddof=0) / close_mean * 100.0) if len(window) > 1 and close_mean > 0 else None
    start_high = float(window["high"].iloc[0])
    resistance_pass = bool(start_high >= base_high * (1.0 - resistance_tolerance_pct / 100.0))
    depth_pass = bool(depth_pct <= max_depth_pct)
    end_near_high_pass = bool(current_vs_high_pct >= -max_end_drawdown_pct)
    atr_contraction_pass = bool(atr_ratio is not None and atr_ratio <= 1.0)
    range_contraction_pass = bool(range_ratio is not None and range_ratio <= 1.0)
    quality = _quality_score(depth_pct, current_vs_high_pct, atr_ratio, range_ratio, len(window), max_depth_pct, max_end_drawdown_pct)
    detected = depth_pass and end_near_high_pass and resistance_pass
    return GenericBaseSnapshot(
        status=BASE_DETECTED if detected else NO_BASE,
        measurement=MEASUREMENT,
        status_reason="depth/end/resistance conditions satisfied" if detected else "candidate window requires diagnostic classification",
        base_start_date=pd.Timestamp(window.index[0]).strftime("%Y-%m-%d"),
        base_end_date=pd.Timestamp(window.index[-1]).strftime("%Y-%m-%d"),
        base_duration_sessions=int(len(window)),
        base_high_date=pd.Timestamp(high_date).strftime("%Y-%m-%d"),
        base_high=base_high,
        base_low_date=pd.Timestamp(low_date).strftime("%Y-%m-%d"),
        base_low=base_low,
        base_depth_pct=depth_pct,
        current_vs_base_high_pct=current_vs_high_pct,
        atr_early_pct=atr_early,
        atr_late_pct=atr_late,
        atr_contraction_ratio=atr_ratio,
        range_early_pct=range_early,
        range_late_pct=range_late,
        range_contraction_ratio=range_ratio,
        close_dispersion_pct=close_dispersion,
        experimental_quality_score=quality,
        experimental_depth_pass=depth_pass,
        experimental_end_near_high_pass=end_near_high_pass,
        experimental_resistance_pass=resistance_pass,
        experimental_atr_contraction_pass=atr_contraction_pass,
        experimental_range_contraction_pass=range_contraction_pass,
        filter_applied=False,
    )


def _empty(status: str = INSUFFICIENT) -> GenericBaseSnapshot:
    return GenericBaseSnapshot(status, MEASUREMENT, "insufficient history", None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, False, False, False, False, False, False)


def _diagnostic_status(snap: GenericBaseSnapshot, *, loose_ratio: float) -> tuple[str, str]:
    if not snap.experimental_depth_pass:
        return TOO_DEEP, "base depth exceeds experimental maximum"
    if not snap.experimental_end_near_high_pass:
        return TOO_FAR_FROM_HIGH, "current close is too far below base high"
    if (snap.atr_contraction_ratio is not None and snap.atr_contraction_ratio > loose_ratio) or (snap.range_contraction_ratio is not None and snap.range_contraction_ratio > loose_ratio):
        return TOO_LOOSE, "late base volatility/range expanded beyond loose threshold"
    if not snap.experimental_resistance_pass:
        return NO_RESISTANCE_ANCHOR, "base start is not near the later resistance high"
    return NO_BASE, "no candidate satisfied the complete generic-base definition"


def _diagnostic_rank(snap: GenericBaseSnapshot) -> tuple:
    core_passes = sum([bool(snap.experimental_depth_pass), bool(snap.experimental_end_near_high_pass), bool(snap.experimental_resistance_pass)])
    contraction_passes = sum([bool(snap.experimental_atr_contraction_pass), bool(snap.experimental_range_contraction_pass)])
    return (core_passes, contraction_passes, snap.experimental_quality_score or -1.0, -(snap.base_duration_sessions or 0))


def compute_generic_base_snapshot(df: pd.DataFrame, *, min_base_sessions: int = 15, max_base_sessions: int = 60, experimental_max_depth_pct: float = 35.0, experimental_max_end_drawdown_pct: float = 12.0, experimental_resistance_tolerance_pct: float = 3.0, experimental_loose_ratio: float = 1.25, as_of=None) -> GenericBaseSnapshot:
    """Detect a recent consolidation ending at as_of without look-ahead."""
    if min_base_sessions < 5:
        raise ValueError("min_base_sessions must be >= 5")
    if max_base_sessions < min_base_sessions:
        raise ValueError("max_base_sessions must be >= min_base_sessions")
    history = _normalize_history(df, as_of=as_of)
    if len(history) < min_base_sessions:
        return _empty(INSUFFICIENT)
    max_len = min(max_base_sessions, len(history))
    all_candidates = []
    detected = []
    for start_pos in range(len(history) - max_len, len(history) - min_base_sessions + 1):
        snap = _snapshot_from_window(history.iloc[start_pos:].copy(), max_depth_pct=float(experimental_max_depth_pct), max_end_drawdown_pct=float(experimental_max_end_drawdown_pct), resistance_tolerance_pct=float(experimental_resistance_tolerance_pct))
        all_candidates.append(snap)
        if snap.status == BASE_DETECTED:
            detected.append(snap)
    if detected:
        return max(detected, key=lambda item: (item.experimental_quality_score or -1.0, item.base_duration_sessions or 0))
    if not all_candidates:
        return _empty(NO_BASE)
    best = max(all_candidates, key=_diagnostic_rank)
    status, reason = _diagnostic_status(best, loose_ratio=float(experimental_loose_ratio))
    values = best.to_dict()
    values["status"] = status
    values["status_reason"] = reason
    return GenericBaseSnapshot(**values)


def link_prior_advance_to_base(base: GenericBaseSnapshot, *, prior_low: float | None, prior_peak: float | None, peak_to_base_sessions: int | None, current_close: float | None) -> AdvanceBaseLinkSnapshot:
    if base.status != BASE_DETECTED or base.base_low is None or prior_low is None or prior_peak is None or current_close is None or prior_low <= 0 or prior_peak <= prior_low or current_close <= 0:
        return AdvanceBaseLinkSnapshot(INSUFFICIENT, None, None, None, None)
    advance_amount = float(prior_peak - prior_low)
    drawdown = (float(base.base_low) / float(prior_peak) - 1.0) * 100.0
    retention = (float(base.base_low) - float(prior_low)) / advance_amount
    current_retention = (float(current_close) - float(prior_low)) / advance_amount
    return AdvanceBaseLinkSnapshot(LINK_AVAILABLE, None if peak_to_base_sessions is None else int(peak_to_base_sessions), drawdown, retention, current_retention)
