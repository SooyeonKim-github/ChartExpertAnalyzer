from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ThresholdOptimization import ThresholdOptimizer
from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.leadership_validation import LeadershipValidationEngine
from leader_stock_analyzer.optimization import LeaderThresholdAdapter


def _history_frame() -> pd.DataFrame:
    rows = []
    for i, date in enumerate(pd.bdate_range("2025-01-02", periods=15)):
        d = date.strftime("%Y%m%d")
        rows.append(
            {
                "scan_date": d,
                "ticker": "000001",
                "name": "A",
                "status": "CONFIRMED",
                "leader_type": "PERSISTENT_LEADER" if i >= 5 else "NORMAL",
                "leader_score": 82.0,
                "market_leader_rank": 5,
                "trading_value_rank": 5,
                "leader_persistence_level": "HIGH" if i >= 5 else "MEDIUM",
                "lifecycle_state": "PERSISTENT_LEADER" if i >= 5 else "LEADER",
                "sector_context_reliable": True,
                "sector_market_rank": 2,
                "sector_leader_rank": 1,
                "D+5": -2.0,
                "D+20": -5.0,
            }
        )
        rows.append(
            {
                "scan_date": d,
                "ticker": "000002",
                "name": "B",
                "status": "CONFIRMED",
                "leader_type": "NORMAL",
                "leader_score": 75.0 if i == 0 else 50.0,
                "market_leader_rank": 10 if i == 0 else 80,
                "trading_value_rank": 10 if i == 0 else 80,
                "leader_persistence_level": "LOW",
                "lifecycle_state": "DISCOVERY",
                "sector_context_reliable": True,
                "sector_market_rank": 20,
                "sector_leader_rank": 10,
                "D+5": 15.0,
                "D+20": 25.0,
            }
        )
    return pd.DataFrame(rows)


def test_leadership_validation_distinguishes_persistent_and_false_leader():
    engine = LeadershipValidationEngine(DEFAULT_CONFIG)
    out = engine.annotate(_history_frame())

    first_a = out[(out["scan_date"] == "20250102") & (out["ticker"] == "000001")].iloc[0]
    first_b = out[(out["scan_date"] == "20250102") & (out["ticker"] == "000002")].iloc[0]

    assert bool(first_a["leadership_valid_10d"])
    assert first_a["leader_retention_5d"] == 100.0
    assert first_a["market_top20_retention_5d"] == 100.0
    assert first_a["turnover_top20_retention_5d"] == 100.0
    assert bool(first_a["persistence_conversion_10d"])
    assert not bool(first_a["false_leader_5d"])

    assert first_b["leader_retention_5d"] == 0.0
    assert first_b["market_top20_retention_5d"] == 0.0
    assert not bool(first_b["persistence_conversion_10d"])
    assert bool(first_b["false_leader_5d"])


def _optimizer_frame() -> pd.DataFrame:
    rows = []
    for date in pd.bdate_range("2025-01-02", periods=140):
        d = date.strftime("%Y%m%d")
        for leader_score, quality, ret in ((85.0, 100.0, -10.0), (75.0, 0.0, 20.0)):
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
                    "leadership_valid_10d": True,
                    "leader_retention_5d": quality,
                    "market_top20_retention_5d": quality,
                    "turnover_top20_retention_5d": quality,
                    "persistence_conversion_10d": quality > 0,
                    "sector_leader_retention_5d": None,
                    "sector_context_future_coverage_5d": 0.0,
                    "false_leader_5d": quality == 0,
                    "leadership_quality_score": quality,
                    "D+5": ret,
                    "D+20": ret,
                }
            )
    return pd.DataFrame(rows)


def test_leadership_optimizer_prefers_leadership_even_when_return_is_negative():
    cfg = {
        "optimizer": {
            "objective_profile": "leadership_quality",
            "leadership_validity_column": "leadership_valid_10d",
            "min_train_trading_days": 30,
            "validation_trading_days": 20,
            "step_trading_days": 20,
            "purge_trading_days": 10,
            "min_validation_fraction": 0.75,
            "min_train_samples": 5,
            "min_train_unique_dates": 5,
            "min_samples": 5,
            "min_unique_dates": 5,
            "min_valid_folds": 1,
            "acceptable_min_fold_coverage": 0.20,
            "top_n": 10,
            "objective_weights": {
                "leader_retention": 0.30,
                "market_rank_retention": 0.20,
                "persistence_conversion": 0.15,
                "turnover_retention": 0.15,
                "sector_leadership": 0.10,
                "false_leader_quality": 0.10,
            },
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
    adapter = LeaderThresholdAdapter("confirmed", DEFAULT_CONFIG)
    result = ThresholdOptimizer(adapter, cfg).run(_optimizer_frame())

    assert result.recommended_params["confirmed_leader"] == 80
    comparison = result.current_vs_optimized.set_index("config")
    assert comparison.loc["OPTIMIZED", "diag_avg_D20"] < 0
    assert comparison.loc["OPTIMIZED", "leader_retention_5d"] == 100.0
