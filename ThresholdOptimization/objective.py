from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _bool_series(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=bool)
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return series.map(lambda x: str(x).strip().lower() in {"true", "1", "yes", "y"}).fillna(False)


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


def leadership_metrics(
    selected: pd.DataFrame,
    *,
    validity_column: str = "leadership_valid_10d",
    date_column: str = "scan_date",
) -> dict[str, float | int | None]:
    """Aggregate future leadership labels for one threshold selection.

    Price-return columns are included only as diagnostics. They are deliberately
    excluded from the leadership objective map used by LeaderStockAnalyzer.
    """
    if validity_column not in selected.columns:
        raise ValueError(f"leadership validity column missing: {validity_column}")

    valid_mask = _bool_series(selected[validity_column])
    valid = selected[valid_mask].copy()
    count = int(len(valid))
    unique_dates = (
        int(pd.to_datetime(valid[date_column], errors="coerce").dropna().nunique())
        if count and date_column in valid.columns
        else 0
    )

    def mean_col(name: str) -> float | None:
        series = _numeric(valid, name)
        return None if series.empty else float(series.mean())

    persistence = (
        _bool_series(valid["persistence_conversion_10d"])
        if "persistence_conversion_10d" in valid.columns
        else pd.Series(dtype=bool)
    )
    false_leader = (
        _bool_series(valid["false_leader_5d"])
        if "false_leader_5d" in valid.columns
        else pd.Series(dtype=bool)
    )
    persistence_rate = None if persistence.empty else float(persistence.mean() * 100.0)
    false_rate = None if false_leader.empty else float(false_leader.mean() * 100.0)

    d5 = _numeric(valid, "D+5")
    d20 = _numeric(valid, "D+20")

    return {
        "count": count,
        "unique_dates": unique_dates,
        "leader_retention_5d": mean_col("leader_retention_5d"),
        "market_top20_retention_5d": mean_col("market_top20_retention_5d"),
        "turnover_top20_retention_5d": mean_col("turnover_top20_retention_5d"),
        "persistence_conversion_10d_rate": persistence_rate,
        "sector_leader_retention_5d": mean_col("sector_leader_retention_5d"),
        "sector_context_future_coverage_5d": mean_col("sector_context_future_coverage_5d"),
        "false_leader_5d_rate": false_rate,
        "false_leader_quality_5d": None if false_rate is None else 100.0 - false_rate,
        "avg_leadership_quality_score": mean_col("leadership_quality_score"),
        "sample_size_score": math.log1p(count),
        # Secondary return diagnostics only; never part of leadership objective.
        "diag_avg_D5": None if d5.empty else float(d5.mean()),
        "diag_avg_D20": None if d20.empty else float(d20.mean()),
        "diag_median_D20": None if d20.empty else float(d20.median()),
        "diag_win_rate_D20": None if d20.empty else float((d20 > 0).mean() * 100.0),
    }


def add_fold_objective(
    fold_trials: pd.DataFrame,
    weights: dict[str, float],
    metric_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Z-normalize configured metrics within one fold and build an objective."""
    out = fold_trials.copy()
    valid = out["sample_valid"].fillna(False).astype(bool)
    metric_map = metric_map or {
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
