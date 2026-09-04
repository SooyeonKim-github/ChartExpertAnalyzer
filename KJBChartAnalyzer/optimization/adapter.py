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


class KJBThresholdAdapter(BaseThresholdAdapter):
    analyzer_name = "KJBChartAnalyzer"
    date_column = "signal_date"

    def parameter_space(self, optimizer_config: dict) -> dict[str, list[Any]]:
        search = optimizer_config.get("search_space", {}).get("confirmed", {})
        if search:
            return {str(k): list(v) for k, v in search.items()}
        return {
            "selection_min": [65, 67.5, 70, 72.5, 75],
            "timing_min": [65, 70, 72, 75, 80],
            "leader_min": [60, 65, 70, 75, 80],
            "relative_strength_min": [30, 40, 50, 60],
            "risk_max_exclusive": [45, 50, 55, 60, 65],
        }

    def current_parameters(self) -> dict[str, Any]:
        c = self.analyzer_config.get("confirmation_v1", {}) or {}
        return {
            "selection_min": float(c.get("selection_min", 70.0)),
            "timing_min": float(c.get("timing_min", 72.0)),
            "leader_min": float(c.get("leader_min", 70.0)),
            "relative_strength_min": float(c.get("relative_strength_min", 40.0)),
            "risk_max_exclusive": float(c.get("risk_max_exclusive", 60.0)),
        }

    def required_columns(self) -> set[str]:
        return {
            "signal_date",
            "selection_score",
            "timing_score",
            "leader_score",
            "relative_strength_score",
            "risk_score",
            "chase_risk",
        }

    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        c = self.analyzer_config.get("confirmation_v1", {}) or {}
        reject_high_chase = bool(c.get("reject_high_chase", True))
        mask = (
            (_num(df, "selection_score") >= float(params["selection_min"]))
            & (_num(df, "timing_score") >= float(params["timing_min"]))
            & (_num(df, "leader_score") >= float(params["leader_min"]))
            & (_num(df, "relative_strength_score") >= float(params["relative_strength_min"]))
            & (_num(df, "risk_score") < float(params["risk_max_exclusive"]))
        )
        if reject_high_chase:
            mask &= ~df["chase_risk"].astype(str).eq("높음")
        return mask.fillna(False)

    def validate_parameters(self, params: dict[str, Any]) -> bool:
        return (
            float(params["selection_min"]) >= 0
            and float(params["timing_min"]) >= 0
            and float(params["leader_min"]) >= 0
            and float(params["relative_strength_min"]) >= 0
            and float(params["risk_max_exclusive"]) > 0
        )

    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        current = self.analyzer_config.get("confirmation_v1", {}) or {}
        return {
            "confirmation_v1": {
                "selection_min": float(params["selection_min"]),
                "timing_min": float(params["timing_min"]),
                "leader_min": float(params["leader_min"]),
                "relative_strength_min": float(params["relative_strength_min"]),
                "risk_max_exclusive": float(params["risk_max_exclusive"]),
                "reject_high_chase": bool(current.get("reject_high_chase", True)),
            }
        }
