from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ThresholdOptimization import BaseThresholdAdapter  # noqa: E402


def _num(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce")


def _bool(df: pd.DataFrame, column: str) -> pd.Series:
    s = df[column]
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False).astype(bool)
    return s.map(lambda x: str(x).strip().lower() in {"true", "1", "yes", "y"}).fillna(False)


class MAThresholdAdapter(BaseThresholdAdapter):
    analyzer_name = "MAChartAnalyzer"
    date_column = "Actual_Date"

    def parameter_space(self, optimizer_config: dict) -> dict[str, list[Any]]:
        search = optimizer_config.get("search_space", {}).get(self.phase, {})
        if search:
            return {str(k): list(v) for k, v in search.items()}
        if self.phase == "confirmed":
            return {
                "confirmed_score": [65, 70, 75, 80],
                "confirmed_timing_score": [40, 50, 60, 70],
                "max_ma20_distance_pct": [6, 8, 10, 12],
            }
        return {
            "strong_confirmed_score": [75, 80, 85, 90],
            "strong_timing_score": [60, 70, 80, 90],
        }

    def current_parameters(self) -> dict[str, Any]:
        c = self.analyzer_config
        if self.phase == "confirmed":
            return {
                "confirmed_score": float(c.get("confirmed_score", 70)),
                "confirmed_timing_score": float(c.get("confirmed_timing_score", 50)),
                "max_ma20_distance_pct": float(c.get("max_ma20_distance_pct", 10.0)),
            }
        return {
            "strong_confirmed_score": float(c.get("strong_confirmed_score", 80)),
            "strong_timing_score": float(c.get("strong_timing_score", 70)),
        }

    def required_columns(self) -> set[str]:
        return {
            "Actual_Date",
            "Score",
            "Timing_Score",
            "Bull_Regime",
            "Reversal_Regime",
            "Strong_Pullback_Confirmation",
            "Prior_High_Breakout",
            "Long_Bull_Body",
            "Detached_Above_MA",
            "Box_Breakout",
            "Box_Retest_Hold",
            "Sideways",
            "Long_MA_Breakdown",
            "MA20_Distance_Pct",
        }

    def _fixed_confirmable(self, df: pd.DataFrame, max_distance: float) -> pd.Series:
        trend_ok = _bool(df, "Bull_Regime") | _bool(df, "Reversal_Regime")
        prior_high_confirmed = _bool(df, "Prior_High_Breakout") & (
            _bool(df, "Long_Bull_Body") | _bool(df, "Detached_Above_MA")
        )
        confirmed_trigger = (
            _bool(df, "Box_Breakout")
            | _bool(df, "Box_Retest_Hold")
            | _bool(df, "Strong_Pullback_Confirmation")
            | prior_high_confirmed
        )
        sideways_block = _bool(df, "Sideways") & ~(
            _bool(df, "Box_Breakout") | _bool(df, "Box_Retest_Hold")
        )
        distance = _num(df, "MA20_Distance_Pct")
        not_chasing = distance.notna() & (distance <= float(max_distance))
        return (
            trend_ok
            & confirmed_trigger
            & ~_bool(df, "Long_MA_Breakdown")
            & ~sideways_block
            & not_chasing
        )

    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        if self.phase == "confirmed":
            fixed = self._fixed_confirmable(df, float(params["max_ma20_distance_pct"]))
            return (
                fixed
                & (_num(df, "Score") >= float(params["confirmed_score"]))
                & (_num(df, "Timing_Score") >= float(params["confirmed_timing_score"]))
            ).fillna(False)

        max_distance = float(
            self.confirmed_floor.get(
                "max_ma20_distance_pct",
                self.analyzer_config.get("max_ma20_distance_pct", 10.0),
            )
        )
        fixed = self._fixed_confirmable(df, max_distance)
        return (
            fixed
            & (_num(df, "Score") >= float(params["strong_confirmed_score"]))
            & (_num(df, "Timing_Score") >= float(params["strong_timing_score"]))
        ).fillna(False)

    def validate_parameters(self, params: dict[str, Any]) -> bool:
        if self.phase != "strong" or not self.confirmed_floor:
            return True
        return (
            float(params["strong_confirmed_score"]) >= float(self.confirmed_floor.get("confirmed_score", 0))
            and float(params["strong_timing_score"]) >= float(self.confirmed_floor.get("confirmed_timing_score", 0))
        )

    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.phase == "confirmed":
            return {
                "confirmed_score": int(round(float(params["confirmed_score"]))),
                "confirmed_timing_score": int(round(float(params["confirmed_timing_score"]))),
                "max_ma20_distance_pct": float(params["max_ma20_distance_pct"]),
            }
        return {
            "strong_confirmed_score": int(round(float(params["strong_confirmed_score"]))),
            "strong_timing_score": int(round(float(params["strong_timing_score"]))),
        }
