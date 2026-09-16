from types import SimpleNamespace

import pandas as pd
import pytest

from run_threshold_optimizer import (
    _apply_performance_gate,
    _apply_stage_overrides,
    _performance_gate,
    add_close_path_excursions,
)


def _path_frame(values):
    row = {f"D+{i}": values[i - 1] for i in range(1, 21)}
    return pd.DataFrame([row])


def test_add_close_path_excursions_uses_direction_adjusted_d20_path():
    values = [0.01, -0.02, 0.03, -0.04, 0.08] + [0.02] * 15
    out = add_close_path_excursions(_path_frame(values), horizon=20)

    assert out.loc[0, "close_MFE_D20"] == pytest.approx(0.08)
    assert out.loc[0, "close_MAE_D20"] == pytest.approx(-0.04)
    assert out.loc[0, "close_excursion_ratio_D20"] == pytest.approx(2.0)


def test_excursion_ratio_is_bounded_when_mae_is_near_zero():
    values = [0.01, 0.02, 0.03, 0.04, 0.05] + [0.02] * 15
    out = add_close_path_excursions(_path_frame(values), horizon=20)

    assert out.loc[0, "close_MAE_D20"] == pytest.approx(0.0)
    assert out.loc[0, "close_excursion_ratio_D20"] == pytest.approx(10.0)


def test_stage3_walk_forward_override_is_applied_without_mutating_base():
    base = {
        "optimizer": {
            "validation_trading_days": 126,
            "min_samples": 10,
        },
        "stage_overrides": {
            "stage3": {
                "validation_trading_days": 252,
                "min_samples": 4,
            }
        },
    }

    stage3 = _apply_stage_overrides(base, 3)

    assert stage3["optimizer"]["validation_trading_days"] == 252
    assert stage3["optimizer"]["min_samples"] == 4
    assert base["optimizer"]["validation_trading_days"] == 126
    assert base["optimizer"]["min_samples"] == 10


def test_stage2_can_expand_validation_window_without_changing_common_config():
    base = {
        "optimizer": {
            "validation_trading_days": 126,
            "step_trading_days": 63,
        },
        "stage_overrides": {
            "stage2": {
                "validation_trading_days": 252,
                "step_trading_days": 126,
            }
        },
    }

    stage2 = _apply_stage_overrides(base, 2)

    assert stage2["optimizer"]["validation_trading_days"] == 252
    assert stage2["optimizer"]["step_trading_days"] == 126
    assert base["optimizer"]["validation_trading_days"] == 126
    assert base["optimizer"]["step_trading_days"] == 63


def test_performance_gate_passes_when_all_absolute_floors_are_met():
    row = pd.Series(
        {
            "mean_median_return": 0.02,
            "mean_win_rate": 58.0,
            "mean_p25_return": -0.01,
        }
    )
    gate = {
        "enabled": True,
        "min_mean_median_return": 0.0,
        "min_mean_win_rate": 52.0,
        "min_mean_p25_return": -0.03,
    }

    passed, failures = _performance_gate(row, gate)

    assert passed is True
    assert failures == []


def test_performance_gate_rejects_stable_but_weak_candidate():
    row = pd.Series(
        {
            "mean_median_return": -0.005,
            "mean_win_rate": 47.8,
            "mean_p25_return": -0.04,
        }
    )
    gate = {
        "enabled": True,
        "min_mean_median_return": 0.0,
        "min_mean_win_rate": 52.0,
        "min_mean_p25_return": -0.03,
    }

    passed, failures = _performance_gate(row, gate)

    assert passed is False
    assert len(failures) == 3
    assert any("median_return" in item for item in failures)
    assert any("win_rate" in item for item in failures)
    assert any("p25_return" in item for item in failures)


def test_gate_fallback_prefers_performance_pass_and_refreshes_diagnostics():
    trials = pd.DataFrame(
        [
            {
                "confirmed_score": 65.0,
                "valid_folds": 14,
                "total_folds": 16,
                "fold_coverage": 0.875,
                "mean_validation_objective": 0.10,
                "std_validation_objective": 0.69,
                "robust_score": -0.30,
                "plateau_neighbor_count": 2,
                "plateau_neighbor_mean": -0.45,
                "plateau_drop": 0.14,
                "current_distance": 0.25,
                "final_score": 0.50,
                "recommendation_quality": "ROBUST",
                "eligible_for_application": True,
                "mean_median_return": 0.033,
                "mean_win_rate": 47.8,
                "mean_p25_return": -0.023,
            },
            {
                "confirmed_score": 72.5,
                "valid_folds": 6,
                "total_folds": 16,
                "fold_coverage": 0.375,
                "mean_validation_objective": 0.39,
                "std_validation_objective": 0.70,
                "robust_score": -0.27,
                "plateau_neighbor_count": 1,
                "plateau_neighbor_mean": -0.58,
                "plateau_drop": 0.31,
                "current_distance": 0.125,
                "final_score": 0.40,
                "recommendation_quality": "PROVISIONAL",
                "eligible_for_application": False,
                "mean_median_return": 0.0548,
                "mean_win_rate": 75.9,
                "mean_p25_return": -0.027,
            },
        ]
    )

    class _Adapter:
        date_column = "scan_date"

        def parameter_space(self, _config):
            return {"confirmed_score": [65.0, 72.5]}

        def export_config(self, params):
            return {"stage3_confirmed_score": float(params["confirmed_score"])}

    class _Splitter:
        def split(self, _dates):
            return []

    optimizer = SimpleNamespace(
        min_valid_folds=2,
        top_n=10,
        adapter=_Adapter(),
        config={},
        splitter=_Splitter(),
        _prepare=lambda df: df,
        _comparison=lambda frame, folds, recommended, quality, eligible: pd.DataFrame(
            [{"confirmed_score": recommended["confirmed_score"], "eligible": eligible}]
        ),
    )
    result = SimpleNamespace(
        all_trials=trials,
        recommended_params={"confirmed_score": 65.0},
        recommended_config={"stage3_confirmed_score": 65.0},
        recommendation_quality="ROBUST",
        eligible_for_application=True,
        recommendation_diagnostics={
            "best_valid_folds": 14,
            "best_fold_coverage": 0.875,
            "used_provisional_fallback": False,
        },
        current_vs_optimized=pd.DataFrame(),
        top_configs=pd.DataFrame(),
        stability_report=pd.DataFrame(),
    )
    frame = pd.DataFrame({"scan_date": pd.to_datetime(["2026-01-02"])})
    gate_cfg = {
        "application_performance_gate": {
            "enabled": True,
            "min_mean_median_return": 0.0,
            "min_mean_win_rate": 52.0,
            "min_mean_p25_return": -0.03,
        }
    }

    out = _apply_performance_gate(result, optimizer, frame, gate_cfg)

    assert out.recommended_params["confirmed_score"] == 72.5
    assert out.eligible_for_application is False
    assert out.recommendation_diagnostics["best_valid_folds"] == 6
    assert out.recommendation_diagnostics["best_fold_coverage"] == pytest.approx(0.375)
    assert out.recommendation_diagnostics["best_performance_gate_pass"] is True
    assert out.recommendation_diagnostics["used_performance_gate_fallback"] is True
