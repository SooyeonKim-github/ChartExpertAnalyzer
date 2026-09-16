from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ThresholdOptimization import BaseThresholdAdapter  # noqa: E402


class DynamicThresholdAdapter(BaseThresholdAdapter):
    """Stage-aware threshold optimizer adapter for Dynamic V2.3.

    V2.3 quality scores have different semantics for Stage1/2/3, so one shared
    threshold must never be optimized across mixed stages. ``target_stage`` is read
    from analyzer_config and defaults to Stage3 because that is the 70% deployment
    decision that most needs validation.
    """

    analyzer_name = "DynamicChartAnalyzer"
    date_column = "signal_date"

    @property
    def target_stage(self) -> int:
        stage = int(self.analyzer_config.get("target_stage", 3))
        if stage not in {1, 2, 3}:
            raise ValueError(f"target_stage must be 1, 2, or 3; got {stage}")
        return stage

    def parameter_space(self, optimizer_config: dict) -> dict[str, list[Any]]:
        stage_key = f"stage{self.target_stage}"
        search_root = optimizer_config.get("search_space", {})
        stage_search = search_root.get(stage_key, {})
        if stage_search:
            return {str(k): list(v) for k, v in stage_search.items()}
        confirmed_search = search_root.get("confirmed", {})
        if confirmed_search:
            return {str(k): list(v) for k, v in confirmed_search.items()}
        return {"confirmed_score": [60, 65, 70, 75, 80]}

    def current_parameters(self) -> dict[str, Any]:
        per_stage_key = f"stage{self.target_stage}_confirmed_score"
        current = self.analyzer_config.get(
            per_stage_key,
            self.analyzer_config.get("confirmed_score", 70.0),
        )
        return {"confirmed_score": float(current)}

    def required_columns(self) -> set[str]:
        return {"signal_date", "side", "stage", "quality_score"}

    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        quality = pd.to_numeric(df["quality_score"], errors="coerce")
        stage = pd.to_numeric(df["stage"], errors="coerce")
        return (
            df["side"].astype(str).eq("LONG")
            & stage.eq(self.target_stage)
            & (quality >= float(params["confirmed_score"]))
        ).fillna(False)

    def validate_parameters(self, params: dict[str, Any]) -> bool:
        try:
            value = float(params["confirmed_score"])
        except (KeyError, TypeError, ValueError):
            return False
        return 0.0 <= value <= 100.0 and self.target_stage in {1, 2, 3}

    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "quality_version": "V2.3",
            "target_stage": self.target_stage,
            f"stage{self.target_stage}_confirmed_score": float(params["confirmed_score"]),
        }
