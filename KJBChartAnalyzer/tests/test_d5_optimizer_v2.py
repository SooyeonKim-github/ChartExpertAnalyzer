from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

KJB_ROOT = Path(__file__).resolve().parents[1]
if str(KJB_ROOT) not in sys.path:
    sys.path.insert(0, str(KJB_ROOT))

from d5_threshold_optimizer_v2 import BASELINE, _confidence, apply_trial


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_date": "2026-01-02",
                "Status": "CONFIRMED",
                "selection_score": 80.0,
                "timing_score": 80.0,
                "relative_strength_score": 70.0,
                "leader_score": 75.0,
                "sector_leader_score": 70.0,
                "market_regime": "range",
                "D+5": 0.01,
                "D+5_excess": 0.005,
            },
            {
                "signal_date": "2026-01-02",
                "Status": "CONFIRMED",
                "selection_score": 80.0,
                "timing_score": 80.0,
                "relative_strength_score": 70.0,
                "leader_score": 75.0,
                "sector_leader_score": 70.0,
                "market_regime": "uptrend",
                "D+5": 0.01,
                "D+5_excess": 0.005,
            },
        ]
    )


def test_regime_is_soft_rank_adjustment_not_hard_filter() -> None:
    params = dict(BASELINE)
    params.update({
        "daily_top_n": 1,
        "range_adjust": 2.0,
        "uptrend_adjust": 0.0,
        "d5_score_min": 68.0,
    })
    out = apply_trial(_frame(), params)

    # Both remain eligible; range only wins the ranking because of the soft adjustment.
    assert out["D5_Eligible"].tolist() == [True, True]
    assert out["market_regime_adjustment"].tolist() == [2.0, 0.0]
    assert out["D5_Selected"].tolist() == [True, False]


def _fold_df(opt_excess, base_excess) -> pd.DataFrame:
    rows = []
    for idx, (opt, base) in enumerate(zip(opt_excess, base_excess), start=1):
        row = {
            "fold": idx,
            "test_avg_excess_D+5": opt,
            "baseline_test_avg_excess_D+5": base,
            "test_sample_count": 40,
        }
        row.update(BASELINE)
        rows.append(row)
    return pd.DataFrame(rows)


def test_confidence_is_provisional_when_optimizer_loses_to_baseline() -> None:
    fold_df = _fold_df(
        [0.004, 0.005, 0.006],
        [0.006, 0.007, 0.008],
    )
    confidence, eligible, stats = _confidence(fold_df)
    assert confidence == "PROVISIONAL"
    assert eligible is False
    assert stats["positive_excess_fold_ratio"] == 1.0
    assert stats["baseline_beat_ratio"] == 0.0
    assert stats["mean_delta_test_avg_excess_D+5"] < 0


def test_confidence_accepts_positive_paired_baseline_improvement() -> None:
    fold_df = _fold_df(
        [0.008, 0.004, 0.007],
        [0.004, 0.005, 0.003],
    )
    confidence, eligible, stats = _confidence(fold_df)
    assert confidence == "ACCEPTABLE"
    assert eligible is True
    assert stats["paired_test_folds"] == 3
    assert stats["baseline_beat_ratio"] >= 0.5
    assert stats["mean_delta_test_avg_excess_D+5"] > 0


def test_confidence_robust_requires_four_stable_folds() -> None:
    fold_df = _fold_df(
        [0.008, 0.007, 0.009, 0.006],
        [0.003, 0.004, 0.005, 0.002],
    )
    confidence, eligible, stats = _confidence(fold_df)
    assert confidence == "ROBUST"
    assert eligible is True
    assert stats["paired_test_folds"] == 4
    assert stats["baseline_beat_ratio"] == 1.0
    assert stats["parameter_stability"] == 1.0
