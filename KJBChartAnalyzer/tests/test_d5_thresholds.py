from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

KJB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = KJB_ROOT.parent
for path in (REPO_ROOT, KJB_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chartsel.selection.confirmation import classify_confirmation_values
from optimization.adapter import KJBThresholdAdapter
from run_threshold_optimizer import _ensure_d5_path_metrics


def _cfg() -> dict:
    return {
        "confirmation_v1": {
            "selection_min": 70,
            "selection_max": 85,
            "timing_min": 72,
            "timing_max": 100,
            "leader_min": 70,
            "leader_max": 80,
            "relative_strength_min": 40,
            "relative_strength_max": 95,
            "risk_max_exclusive": 60,
            "reject_high_chase": True,
            "watch_selection_min": 62,
            "watch_technical_min": 62,
            "watch_risk_max_exclusive": 65,
        }
    }


def test_overextended_score_becomes_watch() -> None:
    common = dict(
        technical_score=75,
        timing_score=75,
        risk_score=40,
        leader_score=75,
        relative_strength_score=80,
        chase_risk="낮음",
        cfg=_cfg(),
    )
    assert classify_confirmation_values(selection_score=80, **common) == "CONFIRMED"
    assert classify_confirmation_values(selection_score=90, **common) == "WATCH"


def test_adapter_applies_min_and_max_thresholds() -> None:
    adapter = KJBThresholdAdapter(phase="confirmed", analyzer_config=_cfg())
    params = adapter.current_parameters()
    frame = pd.DataFrame(
        [
            {
                "signal_date": "20260901",
                "selection_score": 80,
                "timing_score": 75,
                "leader_score": 75,
                "relative_strength_score": 80,
                "risk_score": 40,
                "chase_risk": "낮음",
            },
            {
                "signal_date": "20260901",
                "selection_score": 90,
                "timing_score": 75,
                "leader_score": 75,
                "relative_strength_score": 80,
                "risk_score": 40,
                "chase_risk": "낮음",
            },
        ]
    )
    assert adapter.select_mask(frame, params).tolist() == [True, False]


def test_d5_path_metrics_require_complete_five_days() -> None:
    frame = pd.DataFrame(
        [
            {"D+1": 0.01, "D+2": 0.04, "D+3": 0.06, "D+4": 0.03, "D+5": 0.01},
            {"D+1": -0.02, "D+2": 0.01, "D+3": 0.02, "D+4": 0.03, "D+5": None},
        ]
    )
    out = _ensure_d5_path_metrics(frame)
    assert out.loc[0, "MFE_D5"] == 0.06
    assert out.loc[0, "MAE_D5"] == 0.01
    assert pd.notna(out.loc[0, "excursion_ratio_D5"])
    assert pd.isna(out.loc[1, "MFE_D5"])
    assert pd.isna(out.loc[1, "MAE_D5"])
    assert pd.isna(out.loc[1, "excursion_ratio_D5"])
