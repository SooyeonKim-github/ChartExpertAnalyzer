from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

INTRADAY_AVAILABLE = "AVAILABLE"
INTRADAY_INSUFFICIENT = "INSUFFICIENT"
INTRADAY_IMPROVING = "IMPROVING"
INTRADAY_WEAKENING = "WEAKENING"
INTRADAY_MIXED = "MIXED"

WEAK_OPEN_STRONG_CLOSE = "WEAK_OPEN_STRONG_CLOSE"
STRONG_OPEN_WEAK_CLOSE = "STRONG_OPEN_WEAK_CLOSE"
STRONG_CLOSE = "STRONG_CLOSE"
WEAK_CLOSE = "WEAK_CLOSE"


@dataclass(frozen=True)
class MarketIntradaySnapshot:
    market: str
    status: str
    measurement: str
    gap_return_pct: float | None
    open_close_return_pct: float | None
    close_return_pct: float | None
    close_location_value: float | None
    recovery_strength_pct: float | None
    fade_strength_pct: float | None
    intraday_label: str
    experimental_intraday_strength_score: float | None
    weak_open_strong_close_5d_ratio: float | None
    weak_open_strong_close_20d_ratio: float | None
    strong_open_weak_close_5d_ratio: float | None
    strong_open_weak_close_20d_ratio: float | None
    strong_close_5d_ratio: float | None
    strong_close_20d_ratio: float | None
    weak_close_5d_ratio: float | None
    weak_close_20d_ratio: float | None
    intraday_direction: str

    def to_dict(self) -> dict:
        return asdict(self)


def _float_or_none(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def compute_intraday_strength_history(index_df: pd.DataFrame, *, strong_clv_threshold: float = 0.70, weak_clv_threshold: float = 0.30, short_window: int = 5, long_window: int = 20) -> pd.DataFrame:
    if not 0 <= weak_clv_threshold < strong_clv_threshold <= 1:
        raise ValueError("CLV thresholds must satisfy 0 <= weak < strong <= 1")
    if short_window <= 0 or long_window <= 0 or short_window >= long_window:
        raise ValueError("Intraday rolling windows must satisfy 0 < short < long")

    required = {"open", "high", "low", "close"}
    missing = required.difference(index_df.columns)
    if missing:
        raise ValueError(f"Missing intraday-strength columns: {sorted(missing)}")

    out = index_df[["open", "high", "low", "close"]].copy()
    for col in ["open", "high", "low", "close"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out[(out["open"] > 0) & (out["high"] > 0) & (out["low"] > 0) & (out["close"] > 0)]
    out = out[~out.index.duplicated(keep="last")]
    if out.empty:
        return out

    out["prev_close"] = out["close"].shift(1)
    day_range = out["high"] - out["low"]
    valid_range = day_range.gt(0)
    out["close_location_value"] = pd.NA
    out.loc[valid_range, "close_location_value"] = (out.loc[valid_range, "close"] - out.loc[valid_range, "low"]) / day_range.loc[valid_range]
    out["close_location_value"] = pd.to_numeric(out["close_location_value"], errors="coerce")

    prev_valid = out["prev_close"].gt(0)
    for col in ["gap_return_pct", "close_return_pct", "recovery_strength_pct", "fade_strength_pct"]:
        out[col] = pd.NA
    out.loc[prev_valid, "gap_return_pct"] = (out.loc[prev_valid, "open"] / out.loc[prev_valid, "prev_close"] - 1.0) * 100.0
    out.loc[prev_valid, "close_return_pct"] = (out.loc[prev_valid, "close"] / out.loc[prev_valid, "prev_close"] - 1.0) * 100.0
    out.loc[prev_valid, "recovery_strength_pct"] = ((out.loc[prev_valid, "close"] - out.loc[prev_valid, "low"]) / out.loc[prev_valid, "prev_close"]) * 100.0
    out.loc[prev_valid, "fade_strength_pct"] = ((out.loc[prev_valid, "close"] - out.loc[prev_valid, "high"]) / out.loc[prev_valid, "prev_close"]) * 100.0
    out["open_close_return_pct"] = (out["close"] / out["open"] - 1.0) * 100.0

    clv = out["close_location_value"]
    strong_close_flag = clv.ge(strong_clv_threshold) & out["close"].gt(out["open"])
    weak_close_flag = clv.le(weak_clv_threshold) & out["close"].lt(out["open"])
    weak_open_strong_close_flag = out["gap_return_pct"].lt(0) & strong_close_flag
    strong_open_weak_close_flag = out["gap_return_pct"].gt(0) & weak_close_flag

    labels = []
    for idx, row in out.iterrows():
        if pd.isna(row["prev_close"]) or pd.isna(row["close_location_value"]):
            labels.append(INTRADAY_INSUFFICIENT)
        elif bool(weak_open_strong_close_flag.loc[idx]):
            labels.append(WEAK_OPEN_STRONG_CLOSE)
        elif bool(strong_open_weak_close_flag.loc[idx]):
            labels.append(STRONG_OPEN_WEAK_CLOSE)
        elif bool(strong_close_flag.loc[idx]):
            labels.append(STRONG_CLOSE)
        elif bool(weak_close_flag.loc[idx]):
            labels.append(WEAK_CLOSE)
        else:
            labels.append(INTRADAY_MIXED)
    out["intraday_label"] = labels

    out["is_weak_open_strong_close"] = weak_open_strong_close_flag.astype(float)
    out["is_strong_open_weak_close"] = strong_open_weak_close_flag.astype(float)
    out["is_strong_close"] = strong_close_flag.astype(float)
    out["is_weak_close"] = weak_close_flag.astype(float)

    rolling_specs = {"weak_open_strong_close": "is_weak_open_strong_close", "strong_open_weak_close": "is_strong_open_weak_close", "strong_close": "is_strong_close", "weak_close": "is_weak_close"}
    for name, source in rolling_specs.items():
        out[f"{name}_{short_window}d_ratio"] = out[source].rolling(short_window, min_periods=short_window).mean() * 100.0
        out[f"{name}_{long_window}d_ratio"] = out[source].rolling(long_window, min_periods=long_window).mean() * 100.0

    directions = []
    for _, row in out.iterrows():
        s_short = row.get(f"strong_close_{short_window}d_ratio")
        s_long = row.get(f"strong_close_{long_window}d_ratio")
        w_short = row.get(f"weak_close_{short_window}d_ratio")
        w_long = row.get(f"weak_close_{long_window}d_ratio")
        if any(pd.isna(v) for v in [s_short, s_long, w_short, w_long]):
            directions.append(INTRADAY_INSUFFICIENT)
        elif s_short > s_long and w_short < w_long:
            directions.append(INTRADAY_IMPROVING)
        elif s_short < s_long and w_short > w_long:
            directions.append(INTRADAY_WEAKENING)
        else:
            directions.append(INTRADAY_MIXED)
    out["intraday_direction"] = directions

    body_strength = pd.Series(pd.NA, index=out.index, dtype="Float64")
    body_strength.loc[valid_range] = ((out.loc[valid_range, "close"] - out.loc[valid_range, "open"]) / day_range.loc[valid_range]).clip(-1.0, 1.0)
    body_score = ((body_strength + 1.0) / 2.0) * 100.0
    out["experimental_intraday_strength_score"] = ((out["close_location_value"] * 100.0 * 0.60) + (body_score * 0.40)).clip(0.0, 100.0)
    return out


def latest_intraday_snapshot(history: pd.DataFrame, *, market: str, short_window: int = 5, long_window: int = 20) -> MarketIntradaySnapshot:
    if history is None or history.empty:
        return MarketIntradaySnapshot(str(market).upper(), INTRADAY_INSUFFICIENT, "DAILY_OHLC_PROXY", None, None, None, None, None, None, INTRADAY_INSUFFICIENT, None, None, None, None, None, None, None, None, None, INTRADAY_INSUFFICIENT)
    row = history.iloc[-1]
    label = str(row.get("intraday_label", INTRADAY_INSUFFICIENT))
    status = INTRADAY_AVAILABLE if label != INTRADAY_INSUFFICIENT else INTRADAY_INSUFFICIENT
    return MarketIntradaySnapshot(
        market=str(market).upper(), status=status, measurement="DAILY_OHLC_PROXY",
        gap_return_pct=_float_or_none(row.get("gap_return_pct")), open_close_return_pct=_float_or_none(row.get("open_close_return_pct")), close_return_pct=_float_or_none(row.get("close_return_pct")), close_location_value=_float_or_none(row.get("close_location_value")), recovery_strength_pct=_float_or_none(row.get("recovery_strength_pct")), fade_strength_pct=_float_or_none(row.get("fade_strength_pct")), intraday_label=label,
        experimental_intraday_strength_score=_float_or_none(row.get("experimental_intraday_strength_score")), weak_open_strong_close_5d_ratio=_float_or_none(row.get(f"weak_open_strong_close_{short_window}d_ratio")), weak_open_strong_close_20d_ratio=_float_or_none(row.get(f"weak_open_strong_close_{long_window}d_ratio")), strong_open_weak_close_5d_ratio=_float_or_none(row.get(f"strong_open_weak_close_{short_window}d_ratio")), strong_open_weak_close_20d_ratio=_float_or_none(row.get(f"strong_open_weak_close_{long_window}d_ratio")), strong_close_5d_ratio=_float_or_none(row.get(f"strong_close_{short_window}d_ratio")), strong_close_20d_ratio=_float_or_none(row.get(f"strong_close_{long_window}d_ratio")), weak_close_5d_ratio=_float_or_none(row.get(f"weak_close_{short_window}d_ratio")), weak_close_20d_ratio=_float_or_none(row.get(f"weak_close_{long_window}d_ratio")), intraday_direction=str(row.get("intraday_direction", INTRADAY_INSUFFICIENT)),
    )
