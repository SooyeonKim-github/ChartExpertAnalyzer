import pandas as pd
import pytest

from run_threshold_optimizer import (
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
