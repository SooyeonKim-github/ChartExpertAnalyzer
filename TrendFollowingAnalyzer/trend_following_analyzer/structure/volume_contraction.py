from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

AVAILABLE = "AVAILABLE"
NO_BASE = "NO_BASE"
INSUFFICIENT = "INSUFFICIENT"
MEASUREMENT = "BASE_VOLUME_CONTRACTION_V1"


@dataclass(frozen=True)
class VolumeContractionSnapshot:
    status: str
    measurement: str
    base_start_date: str | None
    base_end_date: str | None
    sessions: int
    volume_early_avg: float | None
    volume_late_avg: float | None
    volume_contraction_ratio: float | None
    volume_early_median: float | None
    volume_late_median: float | None
    volume_median_contraction_ratio: float | None
    volume_5d_vs_20d: float | None
    volume_5d_vs_50d: float | None
    up_day_volume_avg: float | None
    down_day_volume_avg: float | None
    down_vs_up_volume_ratio: float | None
    dry_up_day_ratio: float | None
    experimental_quality_score: float | None
    experimental_contraction_pass: bool
    experimental_down_vs_up_pass: bool
    experimental_dry_up_pass: bool
    filter_applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or not np.isfinite(num) or not np.isfinite(den) or den <= 0:
        return None
    return float(num / den)


def _avg(series: pd.Series) -> float | None:
    x = pd.to_numeric(series, errors="coerce").dropna()
    x = x[x >= 0]
    return None if x.empty else float(x.mean())


def _median(series: pd.Series) -> float | None:
    x = pd.to_numeric(series, errors="coerce").dropna()
    x = x[x >= 0]
    return None if x.empty else float(x.median())


def _empty(status: str, base_start_date: str | None = None) -> VolumeContractionSnapshot:
    return VolumeContractionSnapshot(
        status=status,
        measurement=MEASUREMENT,
        base_start_date=base_start_date,
        base_end_date=None,
        sessions=0,
        volume_early_avg=None,
        volume_late_avg=None,
        volume_contraction_ratio=None,
        volume_early_median=None,
        volume_late_median=None,
        volume_median_contraction_ratio=None,
        volume_5d_vs_20d=None,
        volume_5d_vs_50d=None,
        up_day_volume_avg=None,
        down_day_volume_avg=None,
        down_vs_up_volume_ratio=None,
        dry_up_day_ratio=None,
        experimental_quality_score=None,
        experimental_contraction_pass=False,
        experimental_down_vs_up_pass=False,
        experimental_dry_up_pass=False,
        filter_applied=False,
    )


def compute_volume_contraction_snapshot(
    df: pd.DataFrame,
    *,
    base_status: str,
    base_start_date: str | None,
    as_of=None,
    exclude_last_session: bool = True,
    experimental_max_contraction_ratio: float = 0.80,
    experimental_max_down_vs_up_ratio: float = 1.00,
    experimental_dry_up_volume_ratio: float = 0.70,
    experimental_min_dry_up_day_ratio: float = 0.20,
) -> VolumeContractionSnapshot:
    """Measure whether volume dries up inside a detected base.

    The final session is excluded by default so a breakout-day volume spike does
    not contaminate the pre-breakout contraction measurement.
    """
    if str(base_status) != "BASE_DETECTED" or not base_start_date:
        return _empty(NO_BASE, base_start_date)
    if df is None or df.empty or not {"close", "volume"}.issubset(df.columns):
        return _empty(INSUFFICIENT, base_start_date)

    frame = pd.DataFrame(
        {
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["volume"], errors="coerce"),
        },
        index=pd.to_datetime(df.index, errors="coerce"),
    )
    frame = frame[~frame.index.isna()].sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    if as_of is not None:
        frame = frame[frame.index.normalize() <= pd.Timestamp(as_of).normalize()]
    start = pd.Timestamp(base_start_date).normalize()
    frame = frame[frame.index.normalize() >= start].dropna(subset=["close", "volume"])
    frame = frame[(frame["close"] > 0) & (frame["volume"] >= 0)]
    if exclude_last_session and len(frame) >= 2:
        frame = frame.iloc[:-1].copy()
    if len(frame) < 10:
        return _empty(INSUFFICIENT, base_start_date)

    split = max(5, len(frame) // 2)
    early = frame.iloc[:split]
    late = frame.iloc[split:]
    if late.empty:
        late = frame.iloc[-5:]

    early_avg = _avg(early["volume"])
    late_avg = _avg(late["volume"])
    avg_ratio = _ratio(late_avg, early_avg)
    early_median = _median(early["volume"])
    late_median = _median(late["volume"])
    median_ratio = _ratio(late_median, early_median)

    v5 = _avg(frame["volume"].iloc[-5:]) if len(frame) >= 5 else None
    v20 = _avg(frame["volume"].iloc[-20:]) if len(frame) >= 20 else None
    v50 = _avg(frame["volume"].iloc[-50:]) if len(frame) >= 50 else None
    v5_20 = _ratio(v5, v20)
    v5_50 = _ratio(v5, v50)

    ret = frame["close"].pct_change(fill_method=None)
    up_avg = _avg(frame.loc[ret > 0, "volume"])
    down_avg = _avg(frame.loc[ret < 0, "volume"])
    down_up = _ratio(down_avg, up_avg)

    dry_ref = early_median
    if dry_ref is None or dry_ref <= 0 or late.empty:
        dry_ratio = None
    else:
        dry_threshold = dry_ref * float(experimental_dry_up_volume_ratio)
        dry_ratio = float((late["volume"] <= dry_threshold).mean())

    contraction_pass = bool(
        avg_ratio is not None
        and median_ratio is not None
        and avg_ratio <= float(experimental_max_contraction_ratio)
        and median_ratio <= max(1.0, float(experimental_max_contraction_ratio) + 0.10)
    )
    down_up_pass = bool(
        down_up is not None and down_up <= float(experimental_max_down_vs_up_ratio)
    )
    dry_pass = bool(
        dry_ratio is not None and dry_ratio >= float(experimental_min_dry_up_day_ratio)
    )

    contraction_score = 0.0 if avg_ratio is None else min(1.0, 1.0 / max(avg_ratio, 1e-9))
    down_up_score = 0.5 if down_up is None else min(1.0, 1.0 / max(down_up, 1e-9))
    dry_score = 0.0 if dry_ratio is None else min(1.0, dry_ratio / max(float(experimental_min_dry_up_day_ratio), 1e-9))
    quality = float(100.0 * (0.55 * contraction_score + 0.25 * down_up_score + 0.20 * dry_score))

    return VolumeContractionSnapshot(
        status=AVAILABLE,
        measurement=MEASUREMENT,
        base_start_date=pd.Timestamp(frame.index[0]).strftime("%Y-%m-%d"),
        base_end_date=pd.Timestamp(frame.index[-1]).strftime("%Y-%m-%d"),
        sessions=int(len(frame)),
        volume_early_avg=early_avg,
        volume_late_avg=late_avg,
        volume_contraction_ratio=avg_ratio,
        volume_early_median=early_median,
        volume_late_median=late_median,
        volume_median_contraction_ratio=median_ratio,
        volume_5d_vs_20d=v5_20,
        volume_5d_vs_50d=v5_50,
        up_day_volume_avg=up_avg,
        down_day_volume_avg=down_avg,
        down_vs_up_volume_ratio=down_up,
        dry_up_day_ratio=dry_ratio,
        experimental_quality_score=quality,
        experimental_contraction_pass=contraction_pass,
        experimental_down_vs_up_pass=down_up_pass,
        experimental_dry_up_pass=dry_pass,
        filter_applied=False,
    )
