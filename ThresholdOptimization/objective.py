from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def performance_metrics(
    selected: pd.DataFrame,
    *,
    target_column: str = "D+20",
    mae_column: str = "MAE_D20",
    excursion_column: str = "excursion_ratio_D20",
    date_column: str = "scan_date",
) -> dict[str, float | int | None]:
    target = _numeric(selected, target_column)
    count = int(len(target))
    unique_dates = 0
    if date_column in selected.columns and count:
        tmp = selected.loc[target.index, date_column]
        unique_dates = int(pd.to_datetime(tmp, errors="coerce").dropna().nunique())

    mae = _numeric(selected.loc[target.index] if count else selected, mae_column)
    excursion = _numeric(selected.loc[target.index] if count else selected, excursion_column)
    return {
        "count": count,
        "unique_dates": unique_dates,
        "avg_return": None if target.empty else float(target.mean()),
        "median_return": None if target.empty else float(target.median()),
        "win_rate": None if target.empty else float((target > 0).mean() * 100.0),
        "p25_return": None if target.empty else float(target.quantile(0.25)),
        "p75_return": None if target.empty else float(target.quantile(0.75)),
        "avg_mae": None if mae.empty else float(mae.mean()),
        "mae_quality": None if mae.empty else -abs(float(mae.mean())),
        "avg_excursion_ratio": None if excursion.empty else float(excursion.mean()),
        "sample_size_score": math.log1p(count),
    }


def add_fold_objective(
    fold_trials: pd.DataFrame,
    weights: dict[str, float],
) -> pd.DataFrame:
    """Z-normalize metrics within one fold and build a weighted objective."""
    out = fold_trials.copy()
    valid = out["sample_valid"].fillna(False).astype(bool)
    metric_map = {
        "median_return": "median_return",
        "win_rate": "win_rate",
        "p25_return": "p25_return",
        "mae_quality": "mae_quality",
        "excursion_ratio": "avg_excursion_ratio",
        "sample_size": "sample_size_score",
    }
    score = pd.Series(0.0, index=out.index)
    total_weight = 0.0
    for config_name, column in metric_map.items():
        weight = float(weights.get(config_name, 0.0))
        if weight <= 0 or column not in out.columns:
            continue
        series = pd.to_numeric(out.loc[valid, column], errors="coerce")
        if series.notna().sum() == 0:
            continue
        mean = float(series.mean())
        std = float(series.std(ddof=0))
        z = pd.Series(0.0, index=out.index)
        if std > 1e-12:
            z.loc[valid] = (pd.to_numeric(out.loc[valid, column], errors="coerce") - mean) / std
        else:
            z.loc[valid] = 0.0
        z = z.fillna(0.0)
        out[f"z_{config_name}"] = z
        score += z * weight
        total_weight += weight
    out["objective_score"] = score / total_weight if total_weight > 0 else 0.0
    out.loc[~valid, "objective_score"] = np.nan
    return out
