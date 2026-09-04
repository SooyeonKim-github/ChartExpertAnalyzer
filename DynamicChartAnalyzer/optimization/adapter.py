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
    analyzer_name = "DynamicChartAnalyzer"
    date_column = "signal_date"

    def parameter_space(self, optimizer_config: dict) -> dict[str, list[Any]]:
        search = optimizer_config.get("search_space", {}).get("confirmed", {})
        if search:
            return {str(k): list(v) for k, v in search.items()}
        return {"confirmed_score": [60, 65, 70, 75, 80]}

    def current_parameters(self) -> dict[str, Any]:
        return {"confirmed_score": float(self.analyzer_config.get("confirmed_score", 70.0))}

    def required_columns(self) -> set[str]:
        return {"signal_date", "side", "quality_score"}

    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        quality = pd.to_numeric(df["quality_score"], errors="coerce")
        return (
            df["side"].astype(str).eq("LONG")
            & (quality >= float(params["confirmed_score"]))
        ).fillna(False)

    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"confirmed_score": float(params["confirmed_score"])}
