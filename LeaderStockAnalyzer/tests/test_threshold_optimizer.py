from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ThresholdOptimization import ThresholdOptimizer
from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.optimization import LeaderThresholdAdapter


def _range_frame() -> pd.DataFrame:
    rows = []
    for date in pd.bdate_range("2025-01-02", periods=180):
        d = date.strftime("%Y%m%d")
        for leader_score, ret in ((85.0, 10.0), (75.0, -5.0)):
            rows.append(
                {
                    "scan_date": d,
                    "leader_score": leader_score,
                    "timing_score": 80.0,
                    "chase_risk": 20.0,
                    "breakout_quality_available": False,
                    "breakout_quality_score": None,
                    "breakout_quality_label": "NO_BREAKOUT",
                    "false_breakout_flag": False,
                    "sector_context_available": False,
                    "sector_context_reliable": False,
                    "sector_market_rank": 0,
                    "sector_leader_rank": 0,
                    "persistence_available": False,
                    "leader_persistence_level": "UNKNOWN",
                    "leader_type": "NORMAL",
                    "D+20": ret,
                    "MAE_D20": -2.0 if ret > 0 else -10.0,
                    "excursion_ratio_D20": 4.0 if ret > 0 else 0.5,
                }
            )
    return pd.DataFrame(rows)


def _optimizer_config() -> dict:
    return {
        "optimizer": {
            "target_column": "D+20",
            "mae_column": "MAE_D20",
            "excursion_column": "excursion_ratio_D20",
            "min_train_trading_days": 40,
            "validation_trading_days": 20,
            "step_trading_days": 20,
            "purge_trading_days": 5,
            "min_samples": 5,
            "min_unique_dates": 5,
            "min_valid_folds": 1,
            "top_n": 10,
        },
        "search_space": {
            "confirmed": {
                "confirmed_leader": [75, 80],
                "confirmed_timing": [70],
                "max_chase_risk": [60],
                "min_breakout_quality": [55],
            }
        },
    }


def test_optimizer_prefers_threshold_that_filters_negative_group():
    adapter = LeaderThresholdAdapter("confirmed", DEFAULT_CONFIG)
    optimizer = ThresholdOptimizer(adapter, _optimizer_config())
    result = optimizer.run(_range_frame())
    assert result.recommended_params["confirmed_leader"] == 80
    assert not result.top_configs.empty
    assert set(result.current_vs_optimized["config"]) == {"CURRENT", "OPTIMIZED"}


def test_walk_forward_uses_purge_gap():
    adapter = LeaderThresholdAdapter("confirmed", DEFAULT_CONFIG)
    optimizer = ThresholdOptimizer(adapter, _optimizer_config())
    result = optimizer.run(_range_frame())
    assert not result.folds.empty
    assert (result.folds["purge_days"] == 5).all()


def test_recommended_config_matches_leader_config_shape():
    adapter = LeaderThresholdAdapter("confirmed", DEFAULT_CONFIG)
    optimizer = ThresholdOptimizer(adapter, _optimizer_config())
    result = optimizer.run(_range_frame())
    assert "thresholds" in result.recommended_config
    assert "breakout_quality" in result.recommended_config
    assert "confirmed_leader" in result.recommended_config["thresholds"]
