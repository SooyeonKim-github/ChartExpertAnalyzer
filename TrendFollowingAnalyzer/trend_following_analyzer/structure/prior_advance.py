from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import QUALITY_SUSPECT, assess_price_quality  # noqa: E402

AVAILABLE = "AVAILABLE"
INSUFFICIENT = "INSUFFICIENT"
SUSPECT_DATA = "SUSPECT_DATA"
RECENT_WINDOW_PROXY = "RECENT_WINDOW_PROXY"
BASE_START_ANCHOR = "BASE_START_ANCHOR"


@dataclass(frozen=True)
class PriorAdvanceSnapshot:
    status: str
    measurement: str
    anchor_mode: str
    lookback_sessions: int
    recent_window_sessions: int
    prior_low_date: str | None
    prior_peak_date: str | None
    prior_low: float | None
    prior_peak: float | None
    prior_advance_pct: float | None
    prior_advance_duration_sessions: int | None
    sessions_from_peak_to_anchor: int | None
    current_vs_prior_peak_pct: float | None
    prior_peak_vs_ma150_pct: float | None
    return_60d_pct: float | None
    return_120d_pct: float | None
    experimental_min_advance_pass: bool
    filter_applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_history(df: pd.DataFrame, *, as_of=None) -> pd.DataFrame:
    if df is None or df.empty or "close" not in df.columns:
        return pd.DataFrame(columns=["close", "ma150"])
    out = pd.DataFrame({"close": pd.to_numeric(df["close"], errors="coerce")})
    out["ma150"] = pd.to_numeric(df["ma150"], errors="coerce") if "ma150" in df.columns else pd.NA
    out.index = pd.to_datetime(df.index, errors="coerce")
    out = out[~out.index.isna()]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out[out["close"].gt(0)].dropna(subset=["close"])
    if as_of is not None:
        out = out[out.index.normalize() <= pd.Timestamp(as_of).normalize()]
    return out


def _window_return(close: pd.Series, sessions: int) -> float | None:
    if len(close) < sessions + 1:
        return None
    base = float(close.iloc[-sessions - 1]); current = float(close.iloc[-1])
    if base <= 0:
        return None
    return (current / base - 1.0) * 100.0


def compute_prior_advance_snapshot(df: pd.DataFrame, *, lookback_sessions: int = 120, recent_window_sessions: int = 20, experimental_min_advance_pct: float = 30.0, as_of=None, anchor_date=None, data_quality_jump_threshold_pct: float = 35.0) -> PriorAdvanceSnapshot:
    """Measure prior trough-to-peak advance and flag suspicious price discontinuities."""
    if lookback_sessions < 2:
        raise ValueError("lookback_sessions must be >= 2")
    if recent_window_sessions < 0:
        raise ValueError("recent_window_sessions must be >= 0")
    history = _normalize_history(df, as_of=as_of)
    anchor_mode = BASE_START_ANCHOR if anchor_date is not None else RECENT_WINDOW_PROXY

    def insufficient() -> PriorAdvanceSnapshot:
        return PriorAdvanceSnapshot(status=INSUFFICIENT,measurement="PRE_BASE_TROUGH_TO_PEAK_PROXY",anchor_mode=anchor_mode,lookback_sessions=int(lookback_sessions),recent_window_sessions=int(recent_window_sessions),prior_low_date=None,prior_peak_date=None,prior_low=None,prior_peak=None,prior_advance_pct=None,prior_advance_duration_sessions=None,sessions_from_peak_to_anchor=None,current_vs_prior_peak_pct=None,prior_peak_vs_ma150_pct=None,return_60d_pct=_window_return(history["close"],60) if not history.empty else None,return_120d_pct=_window_return(history["close"],120) if not history.empty else None,experimental_min_advance_pass=False,filter_applied=False)

    if history.empty:
        return insufficient()
    if anchor_date is not None:
        anchor_ts = pd.Timestamp(anchor_date).normalize(); pre = history[history.index.normalize() < anchor_ts].copy(); anchor_position = len(pre)
    else:
        required = lookback_sessions + recent_window_sessions
        if len(history) < required:
            return insufficient()
        anchor_position = len(history) - recent_window_sessions; pre = history.iloc[:anchor_position].copy()
    if len(pre) < lookback_sessions:
        return insufficient()
    window = pre.iloc[-lookback_sessions:].copy()
    quality = assess_price_quality(history[history.index >= window.index[0]].copy(), jump_threshold_pct=float(data_quality_jump_threshold_pct), as_of=as_of)
    closes = window["close"].astype(float); running_min = closes.cummin(); gains = closes / running_min - 1.0
    peak_date = gains.idxmax(); peak_loc = window.index.get_loc(peak_date); before_peak = closes.iloc[:peak_loc + 1]; low_date = before_peak.idxmin()
    low = float(window.loc[low_date,"close"]); peak = float(window.loc[peak_date,"close"])
    if low <= 0:
        return insufficient()
    low_loc = window.index.get_loc(low_date); duration = int(peak_loc - low_loc); advance_pct = (peak / low - 1.0) * 100.0
    peak_global_loc = history.index.get_loc(peak_date); sessions_to_anchor = max(0, int(anchor_position - 1 - peak_global_loc)); current = float(history["close"].iloc[-1]); current_vs_peak = (current / peak - 1.0) * 100.0
    peak_ma150 = history.loc[peak_date,"ma150"] if peak_date in history.index else pd.NA
    peak_vs_ma150 = None if pd.isna(peak_ma150) or float(peak_ma150) <= 0 else (peak / float(peak_ma150) - 1.0) * 100.0
    return PriorAdvanceSnapshot(status=SUSPECT_DATA if quality.status == QUALITY_SUSPECT else AVAILABLE,measurement="PRE_BASE_TROUGH_TO_PEAK_PROXY",anchor_mode=anchor_mode,lookback_sessions=int(lookback_sessions),recent_window_sessions=int(recent_window_sessions),prior_low_date=pd.Timestamp(low_date).strftime("%Y-%m-%d"),prior_peak_date=pd.Timestamp(peak_date).strftime("%Y-%m-%d"),prior_low=low,prior_peak=peak,prior_advance_pct=advance_pct,prior_advance_duration_sessions=duration,sessions_from_peak_to_anchor=sessions_to_anchor,current_vs_prior_peak_pct=current_vs_peak,prior_peak_vs_ma150_pct=peak_vs_ma150,return_60d_pct=_window_return(history["close"],60),return_120d_pct=_window_return(history["close"],120),experimental_min_advance_pass=bool(advance_pct >= float(experimental_min_advance_pct)),filter_applied=False)
