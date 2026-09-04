from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ThresholdOptimization import BaseThresholdAdapter  # noqa: E402


class SwingThresholdAdapter(BaseThresholdAdapter):
    analyzer_name = "SwingChartProbabilityAnalyzer"
    date_column = "Actual_Date"

    ELIGIBLE_SIGNALS = {
        "D10_STRONG_LOWER_CHANNEL_CONFIRMED_REVERSAL",
        "LOWER_CHANNEL_CONFIRMED_REVERSAL_WATCH",
    }

    def parameter_space(self, optimizer_config: dict) -> dict[str, list[Any]]:
        search = optimizer_config.get("search_space", {}).get("confirmed", {})
        if search:
            return {str(k): list(v) for k, v in search.items()}
        return {"confirmed_score": [80, 85, 90, 92, 95]}

    def current_parameters(self) -> dict[str, Any]:
        return {
            "confirmed_score": float(
                self.analyzer_config.get("strong_confirmed_score", 90)
            )
        }

    def required_columns(self) -> set[str]:
        return {"Actual_Date", "Score", "Primary_Signal"}

    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        score = pd.to_numeric(df["Score"], errors="coerce")
        eligible = df["Primary_Signal"].astype(str).isin(self.ELIGIBLE_SIGNALS)
        return (eligible & (score >= float(params["confirmed_score"]))).fillna(False)

    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "strong_confirmed_score": int(round(float(params["confirmed_score"])))
        }
