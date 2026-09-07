from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ThresholdOptimization import BaseThresholdAdapter  # noqa: E402
from chartsel.analysis.overextension import evaluate_overextension  # noqa: E402


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
            "selection_min": [67.5, 70, 72.5],
            "selection_max": [85, 90, 100],
            "timing_min": [70, 72, 75],
            "timing_max": [80, 100],
            "leader_min": [65, 70],
            "leader_max": [80, 85, 100],
            "relative_strength_min": [40, 60],
            "relative_strength_max": [90, 95, 100],
            "risk_max_exclusive": [50, 55, 60],
        }

    def current_parameters(self) -> dict[str, Any]:
        c = self.analyzer_config.get("confirmation_v1", {}) or {}
        return {
            "selection_min": float(c.get("selection_min", 70.0)),
            "selection_max": float(c.get("selection_max", 100.0)),
            "timing_min": float(c.get("timing_min", 72.0)),
            "timing_max": float(c.get("timing_max", 100.0)),
            "leader_min": float(c.get("leader_min", 70.0)),
            "leader_max": float(c.get("leader_max", 100.0)),
            "relative_strength_min": float(c.get("relative_strength_min", 40.0)),
            "relative_strength_max": float(c.get("relative_strength_max", 100.0)),
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

    def _selection_series(self, df: pd.DataFrame) -> pd.Series:
        c = self.analyzer_config.get("confirmation_v1", {}) or {}
        if not bool(c.get("use_d5_score", True)):
            return _num(df, "selection_score")
        if "d5_score" in df.columns:
            return _num(df, "d5_score")

        over_cfg = self.analyzer_config.get("overextension", {}) or {}
        values = []
        for row in df.itertuples(index=False):
            data = row._asdict()
            over = evaluate_overextension(
                selection_score=data.get("selection_score"),
                leader_score=data.get("leader_score"),
                relative_strength_score=data.get("relative_strength_score"),
                chase_risk=data.get("chase_risk", ""),
                cfg=over_cfg,
            )
            values.append(over["d5_score"])
        return pd.Series(values, index=df.index, dtype=float)

    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        c = self.analyzer_config.get("confirmation_v1", {}) or {}
        reject_high_chase = bool(c.get("reject_high_chase", True))
        selection = self._selection_series(df)
        mask = (
            (selection >= float(params["selection_min"]))
            & (selection <= float(params["selection_max"]))
            & (_num(df, "timing_score") >= float(params["timing_min"]))
            & (_num(df, "timing_score") <= float(params["timing_max"]))
            & (_num(df, "leader_score") >= float(params["leader_min"]))
            & (_num(df, "leader_score") <= float(params["leader_max"]))
            & (_num(df, "relative_strength_score") >= float(params["relative_strength_min"]))
            & (_num(df, "relative_strength_score") <= float(params["relative_strength_max"]))
            & (_num(df, "risk_score") < float(params["risk_max_exclusive"]))
        )
        if reject_high_chase:
            mask &= ~df["chase_risk"].astype(str).eq("높음")
        return mask.fillna(False)

    def validate_parameters(self, params: dict[str, Any]) -> bool:
        return (
            0 <= float(params["selection_min"]) <= float(params["selection_max"]) <= 100
            and 0 <= float(params["timing_min"]) <= float(params["timing_max"]) <= 100
            and 0 <= float(params["leader_min"]) <= float(params["leader_max"]) <= 100
            and 0 <= float(params["relative_strength_min"]) <= float(params["relative_strength_max"]) <= 100
            and float(params["risk_max_exclusive"]) > 0
        )

    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        current = dict(self.analyzer_config.get("confirmation_v1", {}) or {})
        current.update({
            "selection_min": float(params["selection_min"]),
            "selection_max": float(params["selection_max"]),
            "timing_min": float(params["timing_min"]),
            "timing_max": float(params["timing_max"]),
            "leader_min": float(params["leader_min"]),
            "leader_max": float(params["leader_max"]),
            "relative_strength_min": float(params["relative_strength_min"]),
            "relative_strength_max": float(params["relative_strength_max"]),
            "risk_max_exclusive": float(params["risk_max_exclusive"]),
        })
        return {"confirmation_v1": current}
