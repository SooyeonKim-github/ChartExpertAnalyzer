from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ThresholdOptimization import BaseThresholdAdapter  # noqa: E402


def _bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)

    def parse(value) -> bool:
        if pd.isna(value):
            return False
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, float, np.integer, np.floating)):
            numeric = float(value)
            if np.isclose(numeric, 1.0):
                return True
            if np.isclose(numeric, 0.0):
                return False
            return False
        return str(value).strip().lower() in {"true", "1", "1.0", "yes", "y"}

    return series.map(parse).fillna(False).astype(bool)


class SwingThresholdAdapter(BaseThresholdAdapter):
    """Threshold-only optimizer adapter for Swing CONFIRMED entries.

    This adapter deliberately keeps the underlying Swing strategy fixed and
    optimizes only the two thresholds that decide whether an otherwise eligible
    lower-channel reversal becomes an actionable CONFIRMED entry:

    1. entry_score (current strong_confirmed_score)
    2. max_entry_channel_position

    Older range exports do not contain Bullish_Turn / Channel_Breakdown flags.
    Therefore confirmation is reconstructed conservatively from persisted
    confirmation features, with the existing confirmed-signal label used only as
    a compatibility fallback for historical rows.
    """

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
        return {
            "entry_score": [80, 82, 84, 86, 88, 90, 92, 94],
            "max_entry_channel_position": [0.35, 0.40, 0.45, 0.50, 0.55, 0.58, 0.60],
        }

    def current_parameters(self) -> dict[str, Any]:
        return {
            "entry_score": float(
                self.analyzer_config.get("strong_confirmed_score", 90)
            ),
            "max_entry_channel_position": float(
                self.analyzer_config.get("max_entry_channel_position", 0.58)
            ),
        }

    def required_columns(self) -> set[str]:
        return {
            "Actual_Date",
            "Score",
            "Primary_Signal",
            "Uptrend_HH_HL",
            "Prior_Low_Held",
            "Recent_Lower_Touch",
            "Channel_Position",
            "Double_Bottom_Confirmed",
            "Reference_High_Break",
            "MA_Reclaimed",
        }

    def _base_eligible(self, df: pd.DataFrame) -> pd.Series:
        uptrend = _bool_series(df["Uptrend_HH_HL"])
        prior_low_held = _bool_series(df["Prior_Low_Held"])
        recent_lower_touch = _bool_series(df["Recent_Lower_Touch"])

        confirmation_proxy = (
            _bool_series(df["Double_Bottom_Confirmed"])
            | _bool_series(df["Reference_High_Break"])
            | _bool_series(df["MA_Reclaimed"])
        )

        known_confirmed_reversal = (
            df["Primary_Signal"].astype(str).isin(self.ELIGIBLE_SIGNALS)
        )
        confirmation_proxy |= known_confirmed_reversal

        return (
            uptrend
            & prior_low_held
            & recent_lower_touch
            & confirmation_proxy
        ).fillna(False)

    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        score = pd.to_numeric(df["Score"], errors="coerce")
        channel_position = pd.to_numeric(df["Channel_Position"], errors="coerce")
        base = self._base_eligible(df)

        return (
            base
            & (score >= float(params["entry_score"]))
            & (
                channel_position
                <= float(params["max_entry_channel_position"])
            )
        ).fillna(False)

    def validate_parameters(self, params: dict[str, Any]) -> bool:
        try:
            entry_score = float(params["entry_score"])
            channel_position = float(params["max_entry_channel_position"])
        except (KeyError, TypeError, ValueError):
            return False
        return 0.0 <= entry_score <= 100.0 and 0.0 <= channel_position <= 1.0

    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "strong_confirmed_score": int(round(float(params["entry_score"]))),
            "max_entry_channel_position": float(
                params["max_entry_channel_position"]
            ),
        }
