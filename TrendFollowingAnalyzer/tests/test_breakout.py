import numpy as np
import pandas as pd

from trend_following_analyzer.structure.breakout import (
    BREAKOUT_CONFIRMED,
    INTRADAY_REJECTED,
    compute_breakout_snapshot,
)


def _frame(last_close=102.0, last_high=103.0, last_volume=2000.0):
    idx = pd.bdate_range("2026-01-02", periods=25)
    prior_close = np.linspace(95.0, 99.0, 24)
    prior_high = np.minimum(prior_close + 1.0, 100.0)
    frame = pd.DataFrame(
        {
            "open": np.r_[prior_close, 100.0],
            "high": np.r_[prior_high, last_high],
            "low": np.r_[prior_close - 1.0, 99.0],
            "close": np.r_[prior_close, last_close],
            "volume": np.r_[np.ones(24) * 1000.0, last_volume],
        },
        index=idx,
    )
    return frame


def test_breakout_requires_close_and_volume_confirmation():
    frame = _frame()
    snap = compute_breakout_snapshot(
        frame,
        pre_base_status="BASE_DETECTED",
        pre_base_start_date=str(frame.index[0].date()),
        experimental_min_volume_ratio=1.5,
    )
    assert snap.status == BREAKOUT_CONFIRMED
    assert snap.close_breakout_pct > 0
    assert snap.breakout_volume_ratio >= 1.5
    assert snap.experimental_signal_pass is True
    assert snap.filter_applied is False


def test_intraday_breakout_rejection_is_explicit():
    frame = _frame(last_close=99.0, last_high=102.0, last_volume=1800.0)
    snap = compute_breakout_snapshot(
        frame,
        pre_base_status="BASE_DETECTED",
        pre_base_start_date=str(frame.index[0].date()),
    )
    assert snap.status == INTRADAY_REJECTED
    assert snap.experimental_false_breakout is True
    assert snap.experimental_signal_pass is False
