from __future__ import annotations

import pandas as pd

from ThresholdOptimization import BaseThresholdAdapter, ThresholdOptimizer
from ThresholdOptimization.walk_forward import PurgedWalkForwardSplitter


class _FakeAdapter(BaseThresholdAdapter):
    analyzer_name = "FakeAnalyzer"
    date_column = "scan_date"

    def parameter_space(self, optimizer_config):
        return {"score_min": [0.0, 1.0]}

    def current_parameters(self):
        return {"score_min": 0.0}

    def required_columns(self):
        return {"scan_date", "score"}

    def select_mask(self, df, params):
        return pd.to_numeric(df["score"], errors="coerce") >= float(params["score_min"])

    def export_config(self, params):
        return {"score_min": float(params["score_min"])}


def _frame(periods: int) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=periods)
    return pd.DataFrame(
        {
            "scan_date": dates,
            "score": [1.0] * periods,
            "D+20": [2.0] * periods,
            "MAE_D20": [-1.0] * periods,
            "excursion_ratio_D20": [2.0] * periods,
        }
    )


def _config(*, min_train: int, purge: int, validation: int, step: int) -> dict:
    return {
        "optimizer": {
            "target_column": "D+20",
            "mae_column": "MAE_D20",
            "excursion_column": "excursion_ratio_D20",
            "min_train_trading_days": min_train,
            "purge_trading_days": purge,
            "validation_trading_days": validation,
            "step_trading_days": step,
            "min_validation_fraction": 0.75,
            "min_train_samples": 5,
            "min_train_unique_dates": 5,
            "min_samples": 5,
            "min_unique_dates": 5,
            "min_valid_folds": 2,
            "train_top_k": 2,
            "top_n": 2,
            "allow_provisional_fallback": True,
            "acceptable_min_fold_coverage": 0.50,
            "robust_min_valid_folds": 3,
            "robust_min_fold_coverage": 0.75,
            "robust_min_plateau_neighbors": 1,
            "robust_max_plateau_drop": 1.0,
            "objective_weights": {
                "median_return": 0.4,
                "win_rate": 0.2,
                "p25_return": 0.2,
                "mae_quality": 0.1,
                "excursion_ratio": 0.05,
                "sample_size": 0.05,
            },
        }
    }


def test_splitter_drops_tiny_trailing_partial_fold():
    dates = pd.bdate_range("2026-01-02", periods=162)
    splitter = PurgedWalkForwardSplitter(
        min_train_trading_days=60,
        purge_trading_days=20,
        validation_trading_days=40,
        step_trading_days=40,
        min_validation_fraction=0.75,
    )

    folds = splitter.split(dates)

    assert len(folds) == 2
    assert [len(f.validation_dates) for f in folds] == [40, 40]
    assert all(f.validation_fraction == 1.0 for f in folds)


def test_single_valid_fold_is_provisional_and_not_application_eligible():
    adapter = _FakeAdapter(phase="confirmed", analyzer_config={})
    optimizer = ThresholdOptimizer(
        adapter,
        _config(min_train=60, purge=20, validation=40, step=40),
    )

    result = optimizer.run(_frame(120))

    assert result.recommendation_quality == "PROVISIONAL"
    assert result.eligible_for_application is False
    assert result.recommendation_diagnostics["best_valid_folds"] == 1
    assert result.recommendation_diagnostics["required_valid_folds"] == 2


def test_two_valid_folds_are_at_least_acceptable():
    adapter = _FakeAdapter(phase="confirmed", analyzer_config={})
    optimizer = ThresholdOptimizer(
        adapter,
        _config(min_train=40, purge=5, validation=40, step=40),
    )

    result = optimizer.run(_frame(125))

    assert result.recommendation_quality == "ACCEPTABLE"
    assert result.eligible_for_application is True
    assert result.recommendation_diagnostics["best_valid_folds"] >= 2
