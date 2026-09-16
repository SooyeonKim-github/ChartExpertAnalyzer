import pandas as pd
import pytest

from run_threshold_optimizer import (
    _apply_stage_overrides,
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
