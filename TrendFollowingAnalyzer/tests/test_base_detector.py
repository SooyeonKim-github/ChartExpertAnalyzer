import numpy as np
import pandas as pd

from trend_following_analyzer.structure.base_detector import (
    BASE_DETECTED,
    TOO_DEEP,
    compute_generic_base_snapshot,
    link_prior_advance_to_base,
)


def _frame(close):
    close = np.asarray(close, dtype=float)
    idx = pd.bdate_range("2026-01-02", periods=len(close))
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
        },
        index=idx,
    )


def test_detects_recent_shallow_base_and_never_applies_filter():
    close = np.r_[np.linspace(100, 200, 60), 190 + 5 * np.sin(np.linspace(0, 6.28, 40))]
    frame = _frame(close)
    frame.iloc[60, frame.columns.get_loc("high")] = 202.0
    snap = compute_generic_base_snapshot(frame, min_base_sessions=15, max_base_sessions=50)
    assert snap.status == BASE_DETECTED
    assert snap.base_duration_sessions >= 15
    assert snap.filter_applied is False
    assert snap.experimental_quality_score is not None


def test_deep_failed_structure_is_labeled_too_deep():
    close = np.r_[np.linspace(100, 200, 50), np.linspace(195, 120, 40)]
    snap = compute_generic_base_snapshot(
        _frame(close),
        min_base_sessions=15,
        max_base_sessions=50,
        experimental_max_depth_pct=25,
        experimental_max_end_drawdown_pct=10,
    )
    assert snap.status == TOO_DEEP


def test_as_of_ignores_future_rows():
    frame = _frame(np.r_[np.linspace(100, 160, 60), np.ones(30) * 150, np.ones(10) * 400])
    cutoff = frame.index[89]
    a = compute_generic_base_snapshot(frame, as_of=cutoff, min_base_sessions=15, max_base_sessions=50)
    changed = frame.copy()
    changed.loc[frame.index[90]:, ["open", "high", "low", "close"]] = [9999, 10099, 9900, 9999]
    b = compute_generic_base_snapshot(changed, as_of=cutoff, min_base_sessions=15, max_base_sessions=50)
    assert a.to_dict() == b.to_dict()


def test_prior_advance_retention_uses_worst_base_low():
    close = np.r_[np.linspace(100, 200, 60), np.ones(30) * 180]
    frame = _frame(close)
    frame.iloc[60, frame.columns.get_loc("high")] = 200.0
    frame.iloc[70, frame.columns.get_loc("low")] = 170.0
    base = compute_generic_base_snapshot(frame, min_base_sessions=15, max_base_sessions=40)
    assert base.status == BASE_DETECTED
    link = link_prior_advance_to_base(
        base,
        prior_low=100.0,
        prior_peak=200.0,
        peak_to_base_sessions=8,
        current_close=180.0,
    )
    assert link.status == "AVAILABLE"
    assert link.peak_to_base_sessions == 8
    assert abs(link.advance_retention_ratio - ((base.base_low - 100.0) / 100.0)) < 1e-12
    assert abs(link.current_advance_retention_ratio - 0.8) < 1e-12
