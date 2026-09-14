from __future__ import annotations

import numpy as np
import pandas as pd

from ThresholdOptimization import ThresholdOptimizer


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )


def _bool_rate(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None

    def parse(value):
        if pd.isna(value):
            return np.nan
        if isinstance(value, (bool, np.bool_)):
            return 1.0 if bool(value) else 0.0
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return 1.0
        if text in {"false", "0", "no", "n"}:
            return 0.0
        return np.nan

    values = frame[column].map(parse).dropna()
    return None if values.empty else float(values.mean() * 100.0)


def _median(series: pd.Series) -> float | None:
    values = series.dropna()
    return None if values.empty else float(values.median())


def _mean(series: pd.Series) -> float | None:
    values = series.dropna()
    return None if values.empty else float(values.mean())


class SwingThresholdOptimizer(ThresholdOptimizer):
    """Swing-specific objective on top of the shared walk-forward engine.

    The shared optimizer still owns grid search, purged expanding walk-forward,
    train-only ranking, OOS validation, stability scoring, plateau analysis and
    recommendation grading. This class only replaces the return metric set with
    a Swing-specific multi-horizon / path-quality objective.
    """

    DEFAULT_WEIGHTS = {
        "d10_median_return": 0.25,
        "d20_median_return": 0.25,
        "hit_mid_rate": 0.15,
        "hit_prior_high_rate": 0.10,
        "d20_p25_return": 0.10,
        "mae20_quality": 0.10,
        "excursion_ratio": 0.05,
    }

    def __init__(self, adapter, optimizer_config: dict):
        super().__init__(adapter, optimizer_config)
        ocfg = (optimizer_config or {}).get("optimizer", optimizer_config or {})

        self.d10_column = str(
            ocfg.get("d10_column", "D+10_Close_Return_Pct")
        )
        self.d20_column = str(
            ocfg.get("d20_column", "D+20_Close_Return_Pct")
        )
        self.mfe20_column = str(ocfg.get("mfe20_column", "MFE_20D_Pct"))
        self.mae20_column = str(ocfg.get("mae20_column", "MAE_20D_Pct"))
        self.hit_mid_column = str(
            ocfg.get("hit_mid_column", "Hit_Mid_Before_Stop")
        )
        self.hit_prior_high_column = str(
            ocfg.get("hit_prior_high_column", "Hit_PriorHigh_Before_Stop")
        )
        self.stop_hit_column = str(ocfg.get("stop_hit_column", "Stop_Hit"))

        # Keep the shared objective builder, but give it Swing-specific metrics.
        self.objective_metric_map = {
            "d10_median_return": "d10_median_return",
            "d20_median_return": "d20_median_return",
            "hit_mid_rate": "hit_mid_rate",
            "hit_prior_high_rate": "hit_prior_high_rate",
            "d20_p25_return": "d20_p25_return",
            "mae20_quality": "mae20_quality",
            "excursion_ratio": "median_excursion_ratio",
        }
        self.objective_weights = dict(
            ocfg.get("objective_weights", self.DEFAULT_WEIGHTS)
        )
        self.aggregate_metric_names = [
            "count",
            "unique_dates",
            "d10_avg_return",
            "d10_median_return",
            "d10_win_rate",
            "d20_avg_return",
            "d20_median_return",
            "d20_win_rate",
            "d20_p25_return",
            "hit_mid_rate",
            "hit_prior_high_rate",
            "stop_hit_rate",
            "median_mfe20",
            "median_mae20",
            "mae20_quality",
            "median_excursion_ratio",
        ]

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = super()._prepare(df)
        required = {
            self.d10_column,
            self.d20_column,
            self.mfe20_column,
            self.mae20_column,
            self.hit_mid_column,
            self.hit_prior_high_column,
        }
        missing = sorted(required - set(out.columns))
        if missing:
            raise ValueError(
                f"Swing objective input missing columns: {missing}"
            )
        return out

    def _metrics(self, selected: pd.DataFrame) -> dict[str, float | int | None]:
        # D+20 is the completeness anchor. Recent rows without a complete D+20
        # outcome do not contribute to objective or sample-count validity.
        d20_all = _numeric(selected, self.d20_column)
        valid_index = d20_all[d20_all.notna()].index
        valid = selected.loc[valid_index].copy()
        d20 = d20_all.loc[valid_index]
        d10 = _numeric(valid, self.d10_column)
        mfe20 = _numeric(valid, self.mfe20_column)
        mae20 = _numeric(valid, self.mae20_column)

        count = int(len(valid_index))
        if count and self.adapter.date_column in valid.columns:
            unique_dates = int(
                pd.to_datetime(
                    valid[self.adapter.date_column], errors="coerce"
                ).dropna().nunique()
            )
        else:
            unique_dates = 0

        d10_values = d10.dropna()
        d20_values = d20.dropna()
        mae_values = mae20.dropna()

        denom = mae20.abs().replace(0, np.nan)
        excursion = (mfe20 / denom).replace([np.inf, -np.inf], np.nan)

        median_mae = _median(mae20)
        return {
            "count": count,
            "unique_dates": unique_dates,
            "d10_avg_return": _mean(d10),
            "d10_median_return": _median(d10),
            "d10_win_rate": (
                None
                if d10_values.empty
                else float((d10_values > 0).mean() * 100.0)
            ),
            "d20_avg_return": _mean(d20),
            "d20_median_return": _median(d20),
            "d20_win_rate": (
                None
                if d20_values.empty
                else float((d20_values > 0).mean() * 100.0)
            ),
            "d20_p25_return": (
                None
                if d20_values.empty
                else float(d20_values.quantile(0.25))
            ),
            "hit_mid_rate": _bool_rate(valid, self.hit_mid_column),
            "hit_prior_high_rate": _bool_rate(
                valid, self.hit_prior_high_column
            ),
            "stop_hit_rate": _bool_rate(valid, self.stop_hit_column),
            "median_mfe20": _median(mfe20),
            "median_mae20": median_mae,
            "mae20_quality": (
                None if median_mae is None else -abs(float(median_mae))
            ),
            "median_excursion_ratio": _median(excursion),
        }
