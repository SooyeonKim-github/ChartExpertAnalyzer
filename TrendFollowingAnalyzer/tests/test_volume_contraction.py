import numpy as np
import pandas as pd

from trend_following_analyzer.structure.volume_contraction import (
    AVAILABLE,
    NO_BASE,
    compute_volume_contraction_snapshot,
)


def _frame(volumes):
    volumes = np.asarray(volumes, dtype=float)
    close = 100 + np.sin(np.linspace(0, 6, len(volumes)))
    return pd.DataFrame(
        {"close": close, "volume": volumes},
        index=pd.bdate_range("2026-01-02", periods=len(volumes)),
    )


def test_volume_contraction_detects_dry_up_inside_base():
    frame = _frame([1000] * 10 + [500] * 10)
    snap = compute_volume_contraction_snapshot(
        frame,
        base_status="BASE_DETECTED",
        base_start_date=str(frame.index[0].date()),
        exclude_last_session=False,
        experimental_max_contraction_ratio=0.80,
    )
    assert snap.status == AVAILABLE
    assert abs(snap.volume_contraction_ratio - 0.5) < 1e-12
    assert snap.experimental_contraction_pass is True
    assert snap.filter_applied is False


def test_volume_contraction_requires_detected_base():
    frame = _frame([1000] * 20)
    snap = compute_volume_contraction_snapshot(
        frame,
        base_status="TOO_DEEP",
        base_start_date=str(frame.index[0].date()),
    )
    assert snap.status == NO_BASE
    assert snap.experimental_contraction_pass is False
    assert snap.filter_applied is False
