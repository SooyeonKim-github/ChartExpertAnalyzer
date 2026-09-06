from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

AVAILABLE = "AVAILABLE"
LOW_COVERAGE = "LOW_COVERAGE"
INSUFFICIENT = "INSUFFICIENT"
IMPROVING = "IMPROVING"
WEAKENING = "WEAKENING"
MIXED = "MIXED"


@dataclass(frozen=True)
class MarketBreadthSnapshot:
    market: str
    status: str
    measurement: str
    source_mode: str
    membership_mode: str
    source_ticker_count: int
    failed_tickers: int
    universe_count: int
    eligible_count: int
    coverage_ratio: float | None
    new_high_52w_count: int
    new_low_52w_count: int
    new_high_52w_ratio: float | None
    new_low_52w_ratio: float | None
    new_high_low_spread: float | None
    breadth_5d_avg: float | None
    breadth_20d_avg: float | None
    breadth_5d_change: float | None
    breadth_20d_change: float | None
    breadth_direction: str
    snapshot_dates_loaded: int
    snapshot_dates_expected: int
    snapshot_date_coverage_ratio: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _float_or_none(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def compute_52w_breadth_history(history: pd.DataFrame, *, lookback_sessions: int = 252, min_history_sessions: int | None = None, short_window: int = 5, long_window: int = 20) -> pd.DataFrame:
    required = {"date", "ticker", "close"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"Missing breadth columns: {sorted(missing)}")
    min_history = int(min_history_sessions or lookback_sessions)
    if lookback_sessions <= 1 or min_history <= 1 or min_history > lookback_sessions or short_window <= 0 or long_window <= 0:
        raise ValueError("invalid breadth windows")
    out = history[["date", "ticker", "close"]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["ticker"] = out["ticker"].astype(str)
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["date", "ticker", "close"])
    out = out[out["close"] > 0].drop_duplicates(["date", "ticker"], keep="last").sort_values(["ticker", "date"]).reset_index(drop=True)
    if out.empty:
        return pd.DataFrame(columns=["date","universe_count","eligible_count","coverage_ratio","new_high_52w_count","new_low_52w_count","new_high_52w_ratio","new_low_52w_ratio","new_high_low_spread","breadth_5d_avg","breadth_20d_avg","breadth_5d_change","breadth_20d_change","breadth_direction"])
    grouped = out.groupby("ticker", sort=False)["close"]
    out["history_count"] = out.groupby("ticker", sort=False).cumcount() + 1
    out["rolling_52w_high_close"] = grouped.transform(lambda s: s.rolling(lookback_sessions, min_periods=min_history).max())
    out["rolling_52w_low_close"] = grouped.transform(lambda s: s.rolling(lookback_sessions, min_periods=min_history).min())
    out["eligible"] = out["history_count"].ge(min_history) & out["rolling_52w_high_close"].notna() & out["rolling_52w_low_close"].notna()
    out["is_new_high"] = out["eligible"] & out["close"].ge(out["rolling_52w_high_close"])
    out["is_new_low"] = out["eligible"] & out["close"].le(out["rolling_52w_low_close"])
    daily = out.groupby("date", as_index=False).agg(universe_count=("ticker","nunique"), eligible_count=("eligible","sum"), new_high_52w_count=("is_new_high","sum"), new_low_52w_count=("is_new_low","sum")).sort_values("date").reset_index(drop=True)
    denominator = daily["eligible_count"].replace(0, pd.NA).astype("Float64")
    daily["coverage_ratio"] = (daily["eligible_count"] / daily["universe_count"].replace(0, pd.NA)).astype("Float64")
    daily["new_high_52w_ratio"] = (daily["new_high_52w_count"] / denominator * 100.0).astype("Float64")
    daily["new_low_52w_ratio"] = (daily["new_low_52w_count"] / denominator * 100.0).astype("Float64")
    daily["new_high_low_spread"] = daily["new_high_52w_ratio"] - daily["new_low_52w_ratio"]
    daily["breadth_5d_avg"] = daily["new_high_52w_ratio"].rolling(short_window, min_periods=short_window).mean()
    daily["breadth_20d_avg"] = daily["new_high_52w_ratio"].rolling(long_window, min_periods=long_window).mean()
    daily["breadth_5d_change"] = daily["new_high_52w_ratio"] - daily["new_high_52w_ratio"].shift(short_window)
    daily["breadth_20d_change"] = daily["new_high_52w_ratio"] - daily["new_high_52w_ratio"].shift(long_window)
    directions=[]
    for _, row in daily.iterrows():
        ratio,avg5,avg20,change5=row["new_high_52w_ratio"],row["breadth_5d_avg"],row["breadth_20d_avg"],row["breadth_5d_change"]
        if pd.isna(ratio) or pd.isna(avg5) or pd.isna(change5): directions.append(INSUFFICIENT)
        elif change5 > 0 and ratio >= avg5 and (pd.isna(avg20) or avg5 >= avg20): directions.append(IMPROVING)
        elif change5 < 0 and ratio <= avg5 and (pd.isna(avg20) or avg5 <= avg20): directions.append(WEAKENING)
        else: directions.append(MIXED)
    daily["breadth_direction"] = directions
    return daily


def latest_breadth_snapshot(history: pd.DataFrame, *, market: str, min_coverage_ratio: float = 0.60, snapshot_dates_loaded: int = 0, snapshot_dates_expected: int = 0, source_mode: str = "UNKNOWN", membership_mode: str = "UNKNOWN", source_ticker_count: int = 0, failed_tickers: int = 0) -> MarketBreadthSnapshot:
    if not 0 <= min_coverage_ratio <= 1:
        raise ValueError("min_coverage_ratio must be between 0 and 1")
    date_coverage = float(snapshot_dates_loaded) / float(snapshot_dates_expected) if snapshot_dates_expected > 0 else None
    base = dict(market=str(market).upper(), measurement="52W_CLOSE_HIGH_PROXY", source_mode=str(source_mode), membership_mode=str(membership_mode), source_ticker_count=int(source_ticker_count), failed_tickers=int(failed_tickers), snapshot_dates_loaded=int(snapshot_dates_loaded), snapshot_dates_expected=int(snapshot_dates_expected), snapshot_date_coverage_ratio=date_coverage)
    if history is None or history.empty:
        return MarketBreadthSnapshot(status=INSUFFICIENT, universe_count=0, eligible_count=0, coverage_ratio=None, new_high_52w_count=0, new_low_52w_count=0, new_high_52w_ratio=None, new_low_52w_ratio=None, new_high_low_spread=None, breadth_5d_avg=None, breadth_20d_avg=None, breadth_5d_change=None, breadth_20d_change=None, breadth_direction=INSUFFICIENT, **base)
    row=history.iloc[-1]
    coverage=_float_or_none(row.get("coverage_ratio")); eligible=int(row.get("eligible_count",0) or 0); ratio=_float_or_none(row.get("new_high_52w_ratio"))
    status=INSUFFICIENT if eligible <= 0 or ratio is None else (LOW_COVERAGE if coverage is not None and coverage < min_coverage_ratio else AVAILABLE)
    return MarketBreadthSnapshot(status=status, universe_count=int(row.get("universe_count",0) or 0), eligible_count=eligible, coverage_ratio=coverage, new_high_52w_count=int(row.get("new_high_52w_count",0) or 0), new_low_52w_count=int(row.get("new_low_52w_count",0) or 0), new_high_52w_ratio=ratio, new_low_52w_ratio=_float_or_none(row.get("new_low_52w_ratio")), new_high_low_spread=_float_or_none(row.get("new_high_low_spread")), breadth_5d_avg=_float_or_none(row.get("breadth_5d_avg")), breadth_20d_avg=_float_or_none(row.get("breadth_20d_avg")), breadth_5d_change=_float_or_none(row.get("breadth_5d_change")), breadth_20d_change=_float_or_none(row.get("breadth_20d_change")), breadth_direction=str(row.get("breadth_direction",INSUFFICIENT)), **base)
