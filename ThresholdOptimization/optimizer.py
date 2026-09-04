from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .base import BaseThresholdAdapter
from .objective import add_fold_objective, performance_metrics
from .walk_forward import PurgedWalkForwardSplitter


def _native(value):
    if isinstance(value, dict):
        return {str(k): _native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if pd.isna(value) if not isinstance(value, (str, bool)) else False:
        return None
    return value


@dataclass
class OptimizationResult:
    recommended_params: dict[str, Any]
    recommended_config: dict[str, Any]
    all_trials: pd.DataFrame
    fold_results: pd.DataFrame
    folds: pd.DataFrame
    current_vs_optimized: pd.DataFrame
    top_configs: pd.DataFrame
    stability_report: pd.DataFrame

    def write(self, out_dir: str | Path) -> dict[str, Path]:
        root = Path(out_dir)
        root.mkdir(parents=True, exist_ok=True)
        files = {
            "all_trials": root / "all_trials.csv",
            "fold_results": root / "fold_results.csv",
            "walk_forward_folds": root / "walk_forward_folds.csv",
            "top_configs": root / "top_configs.csv",
            "stability_report": root / "stability_report.csv",
            "current_vs_optimized": root / "current_vs_optimized.csv",
            "recommended_thresholds": root / "recommended_thresholds.yaml",
        }
        self.all_trials.to_csv(files["all_trials"], index=False, encoding="utf-8-sig")
        self.fold_results.to_csv(files["fold_results"], index=False, encoding="utf-8-sig")
        self.folds.to_csv(files["walk_forward_folds"], index=False, encoding="utf-8-sig")
        self.top_configs.to_csv(files["top_configs"], index=False, encoding="utf-8-sig")
        self.stability_report.to_csv(files["stability_report"], index=False, encoding="utf-8-sig")
        self.current_vs_optimized.to_csv(files["current_vs_optimized"], index=False, encoding="utf-8-sig")
        files["recommended_thresholds"].write_text(
            yaml.safe_dump(_native(self.recommended_config), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return files


class ThresholdOptimizer:
    def __init__(self, adapter: BaseThresholdAdapter, optimizer_config: dict):
        self.adapter = adapter
        self.config = optimizer_config or {}
        ocfg = self.config.get("optimizer", self.config)
        self.target_column = str(ocfg.get("target_column", "D+20"))
        self.mae_column = str(ocfg.get("mae_column", "MAE_D20"))
        self.excursion_column = str(ocfg.get("excursion_column", "excursion_ratio_D20"))
        self.min_samples = int(ocfg.get("min_samples", 30))
        self.min_unique_dates = int(ocfg.get("min_unique_dates", 15))
        self.min_valid_folds = int(ocfg.get("min_valid_folds", 1))
        self.top_n = int(ocfg.get("top_n", 50))
        self.std_penalty = float(ocfg.get("robustness_std_penalty", 0.50))
        self.plateau_penalty = float(ocfg.get("plateau_penalty", 0.20))
        self.distance_penalty = float(ocfg.get("distance_penalty", 0.10))
        self.coverage_penalty = float(ocfg.get("coverage_penalty", 0.50))
        self.objective_weights = dict(
            ocfg.get(
                "objective_weights",
                {
                    "median_return": 0.30,
                    "win_rate": 0.20,
                    "p25_return": 0.15,
                    "mae_quality": 0.15,
                    "excursion_ratio": 0.10,
                    "sample_size": 0.10,
                },
            )
        )
        self.splitter = PurgedWalkForwardSplitter(
            min_train_trading_days=int(ocfg.get("min_train_trading_days", 60)),
            validation_trading_days=int(ocfg.get("validation_trading_days", 40)),
            step_trading_days=int(ocfg.get("step_trading_days", 40)),
            purge_trading_days=int(ocfg.get("purge_trading_days", 20)),
        )

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        self.adapter.validate_dataframe(df)
        if self.target_column not in df.columns:
            raise ValueError(f"optimizer target column missing: {self.target_column}")
        out = df.copy()
        out[self.adapter.date_column] = pd.to_datetime(out[self.adapter.date_column], errors="coerce").dt.normalize()
        out = out[out[self.adapter.date_column].notna()].copy()
        out[self.target_column] = pd.to_numeric(out[self.target_column], errors="coerce")
        return out.sort_values(self.adapter.date_column).reset_index(drop=True)

    def _grid(self, space: dict[str, list[Any]]) -> list[dict[str, Any]]:
        names = list(space)
        values = [list(space[name]) for name in names]
        rows: list[dict[str, Any]] = []
        for combo in product(*values):
            params = dict(zip(names, combo))
            if self.adapter.validate_parameters(params):
                rows.append(params)
        if not rows:
            raise ValueError(f"{self.adapter.analyzer_name}/{self.adapter.phase}: empty valid search grid")
        return rows

    def _fold_table(self, folds) -> pd.DataFrame:
        rows = []
        for fold in folds:
            rows.append(
                {
                    "fold_id": fold.fold_id,
                    "train_start": fold.train_start.date(),
                    "train_end": fold.train_end.date(),
                    "purge_days": len(fold.purge_dates),
                    "validation_start": fold.validation_start.date(),
                    "validation_end": fold.validation_end.date(),
                    "train_trading_days": len(fold.train_dates),
                    "validation_trading_days": len(fold.validation_dates),
                }
            )
        return pd.DataFrame(rows)

    def _evaluate_fold(self, frame: pd.DataFrame, fold, grid: list[dict[str, Any]]) -> pd.DataFrame:
        validation_dates = set(fold.validation_dates)
        val = frame[frame[self.adapter.date_column].isin(validation_dates)].copy()
        rows: list[dict[str, Any]] = []
        for params in grid:
            mask = self.adapter.select_mask(val, params).reindex(val.index, fill_value=False).fillna(False).astype(bool)
            selected = val[mask].copy()
            metrics = performance_metrics(
                selected,
                target_column=self.target_column,
                mae_column=self.mae_column,
                excursion_column=self.excursion_column,
                date_column=self.adapter.date_column,
            )
            sample_valid = (
                int(metrics["count"] or 0) >= self.min_samples
                and int(metrics["unique_dates"] or 0) >= self.min_unique_dates
            )
            rows.append(
                {
                    **params,
                    **metrics,
                    "fold_id": fold.fold_id,
                    "validation_start": fold.validation_start,
                    "validation_end": fold.validation_end,
                    "sample_valid": sample_valid,
                }
            )
        return add_fold_objective(pd.DataFrame(rows), self.objective_weights)

    def _aggregate(self, fold_results: pd.DataFrame, space: dict[str, list[Any]], total_folds: int) -> pd.DataFrame:
        param_cols = list(space)
        rows: list[dict[str, Any]] = []
        for keys, grp in fold_results.groupby(param_cols, dropna=False, sort=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            params = dict(zip(param_cols, keys))
            valid = grp[grp["sample_valid"].fillna(False).astype(bool) & grp["objective_score"].notna()].copy()
            objectives = pd.to_numeric(valid["objective_score"], errors="coerce").dropna()
            valid_folds = int(len(objectives))
            coverage = valid_folds / total_folds if total_folds else 0.0
            mean_obj = float(objectives.mean()) if not objectives.empty else np.nan
            std_obj = float(objectives.std(ddof=0)) if not objectives.empty else np.nan
            robust = (
                mean_obj - self.std_penalty * std_obj - self.coverage_penalty * (1.0 - coverage)
                if valid_folds >= self.min_valid_folds and np.isfinite(mean_obj)
                else np.nan
            )
            row: dict[str, Any] = {
                **params,
                "valid_folds": valid_folds,
                "total_folds": total_folds,
                "fold_coverage": round(coverage, 4),
                "mean_validation_objective": mean_obj,
                "std_validation_objective": std_obj,
                "robust_score": robust,
                "current_distance": self.adapter.parameter_distance(params, space),
            }
            for metric in (
                "count", "unique_dates", "avg_return", "median_return", "win_rate",
                "p25_return", "p75_return", "avg_mae", "avg_excursion_ratio",
            ):
                vals = pd.to_numeric(valid.get(metric, pd.Series(dtype=float)), errors="coerce").dropna()
                row[f"mean_{metric}"] = float(vals.mean()) if not vals.empty else np.nan
            rows.append(row)
        out = pd.DataFrame(rows)
        return self._add_plateau(out, space)

    def _add_plateau(self, trials: pd.DataFrame, space: dict[str, list[Any]]) -> pd.DataFrame:
        out = trials.copy()
        param_cols = list(space)
        lookup = {tuple(row[c] for c in param_cols): idx for idx, row in out.iterrows()}
        neighbor_counts: list[int] = []
        neighbor_means: list[float] = []
        plateau_drops: list[float] = []
        final_scores: list[float] = []

        for _, row in out.iterrows():
            robust = pd.to_numeric(pd.Series([row.get("robust_score")]), errors="coerce").iloc[0]
            neighbors: list[float] = []
            base = [row[c] for c in param_cols]
            for pos, name in enumerate(param_cols):
                ordered = list(space[name])
                try:
                    value_idx = ordered.index(row[name])
                except ValueError:
                    continue
                for offset in (-1, 1):
                    ni = value_idx + offset
                    if ni < 0 or ni >= len(ordered):
                        continue
                    key = list(base)
                    key[pos] = ordered[ni]
                    idx = lookup.get(tuple(key))
                    if idx is None:
                        continue
                    nscore = pd.to_numeric(pd.Series([out.loc[idx, "robust_score"]]), errors="coerce").iloc[0]
                    if pd.notna(nscore):
                        neighbors.append(float(nscore))
            neighbor_mean = float(np.mean(neighbors)) if neighbors else np.nan
            drop = max(0.0, float(robust) - neighbor_mean) if pd.notna(robust) and np.isfinite(neighbor_mean) else 0.0
            distance = float(row.get("current_distance", 0.0) or 0.0)
            final = float(robust) - self.plateau_penalty * drop - self.distance_penalty * distance if pd.notna(robust) else np.nan
            neighbor_counts.append(len(neighbors))
            neighbor_means.append(neighbor_mean)
            plateau_drops.append(drop)
            final_scores.append(final)
        out["plateau_neighbor_count"] = neighbor_counts
        out["plateau_neighbor_mean"] = neighbor_means
        out["plateau_drop"] = plateau_drops
        out["final_score"] = final_scores
        return out.sort_values("final_score", ascending=False, na_position="last").reset_index(drop=True)

    def _comparison(self, frame: pd.DataFrame, folds, recommended: dict[str, Any]) -> pd.DataFrame:
        validation_dates: set[pd.Timestamp] = set()
        for fold in folds:
            validation_dates.update(fold.validation_dates)
        eval_frame = frame[frame[self.adapter.date_column].isin(validation_dates)].copy()
        rows = []
        for label, params in (
            ("CURRENT", self.adapter.current_parameters()),
            ("OPTIMIZED", recommended),
        ):
            mask = self.adapter.select_mask(eval_frame, params).reindex(eval_frame.index, fill_value=False).fillna(False).astype(bool)
            metrics = performance_metrics(
                eval_frame[mask],
                target_column=self.target_column,
                mae_column=self.mae_column,
                excursion_column=self.excursion_column,
                date_column=self.adapter.date_column,
            )
            rows.append({"config": label, **params, **metrics})
        return pd.DataFrame(rows)

    def run(self, df: pd.DataFrame) -> OptimizationResult:
        frame = self._prepare(df)
        folds = self.splitter.split(frame[self.adapter.date_column])
        if not folds:
            raise ValueError(
                "No walk-forward fold could be created. Increase the range or reduce "
                "min_train/validation/purge trading days in optimizer config."
            )
        space = self.adapter.parameter_space(self.config)
        grid = self._grid(space)
        fold_frames = [self._evaluate_fold(frame, fold, grid) for fold in folds]
        fold_results = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
        trials = self._aggregate(fold_results, space, len(folds))
        valid = trials[trials["final_score"].notna() & (trials["valid_folds"] >= self.min_valid_folds)].copy()
        if valid.empty:
            raise ValueError(
                "No threshold combination passed sample/fold requirements. "
                "Use a longer range or relax optimizer min_samples/min_unique_dates."
            )
        best = valid.iloc[0]
        recommended = {name: _native(best[name]) for name in space}
        comparison = self._comparison(frame, folds, recommended)
        top = valid.head(self.top_n).copy()
        stability_cols = list(space) + [
            "valid_folds", "fold_coverage", "mean_validation_objective",
            "std_validation_objective", "robust_score", "plateau_neighbor_count",
            "plateau_neighbor_mean", "plateau_drop", "current_distance", "final_score",
        ]
        stability = valid[[c for c in stability_cols if c in valid.columns]].head(min(20, len(valid))).copy()
        return OptimizationResult(
            recommended_params=recommended,
            recommended_config=self.adapter.export_config(recommended),
            all_trials=trials,
            fold_results=fold_results,
            folds=self._fold_table(folds),
            current_vs_optimized=comparison,
            top_configs=top,
            stability_report=stability,
        )
