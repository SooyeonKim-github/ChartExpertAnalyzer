from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ThresholdOptimization import BaseThresholdAdapter  # noqa: E402


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def _bool(df: pd.DataFrame, col: str) -> pd.Series:
    s = df[col]
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False).astype(bool)
    return s.map(lambda x: str(x).strip().lower() in {"true", "1", "yes", "y"}).fillna(False)


class LeaderThresholdAdapter(BaseThresholdAdapter):
    analyzer_name = "LeaderStockAnalyzer"
    date_column = "scan_date"

    def parameter_space(self, optimizer_config: dict) -> dict[str, list[Any]]:
        search = optimizer_config.get("search_space", {})
        phase_space = search.get(self.phase, {})
        if phase_space:
            return {str(k): list(v) for k, v in phase_space.items()}
        if self.phase == "confirmed":
            return {
                "confirmed_leader": [70, 72.5, 75, 77.5, 80, 82.5],
                "confirmed_timing": [60, 65, 70, 75, 80],
                "max_chase_risk": [40, 50, 60, 70],
                "min_breakout_quality": [45, 55, 65, 70],
            }
        return {
            "strong_leader": [82.5, 85, 87.5, 90],
            "strong_timing": [72.5, 75, 77.5, 80],
            "max_chase_risk": [40, 50, 60],
            "min_breakout_quality": [65, 70, 75, 80],
            "strong_rank_max": [3, 5, 10],
        }

    def current_parameters(self) -> dict[str, Any]:
        t = self.analyzer_config["thresholds"]
        bq = self.analyzer_config.get("breakout_quality", {}).get("confirmation", {})
        if self.phase == "confirmed":
            return {
                "confirmed_leader": float(t["confirmed_leader"]),
                "confirmed_timing": float(t["confirmed_timing"]),
                "max_chase_risk": float(t["max_confirmed_chase_risk"]),
                "min_breakout_quality": float(bq.get("min_confirmed_quality", 55.0)),
            }
        return {
            "strong_leader": float(t["strong_confirmed_leader"]),
            "strong_timing": float(t["strong_confirmed_timing"]),
            "max_chase_risk": float(t["max_confirmed_chase_risk"]),
            "min_breakout_quality": float(bq.get("min_strong_quality", 70.0)),
            "strong_rank_max": int(t["strong_rank_max"]),
        }

    def required_columns(self) -> set[str]:
        cols = {
            "scan_date", "leader_score", "timing_score", "chase_risk",
            "breakout_quality_available", "breakout_quality_score",
            "breakout_quality_label", "false_breakout_flag",
            "sector_context_available", "sector_context_reliable",
            "sector_market_rank", "sector_leader_rank",
            "persistence_available", "leader_persistence_level", "leader_type",
        }
        if self.phase == "strong":
            cols.add("market_leader_rank")
        return cols

    def _quality_gate(self, df: pd.DataFrame, threshold: float) -> pd.Series:
        available = _bool(df, "breakout_quality_available")
        score = _num(df, "breakout_quality_score")
        failed = df["breakout_quality_label"].astype(str).eq("FAILED_BREAKOUT")
        false_break = _bool(df, "false_breakout_flag")
        pass_when_breakout = (score >= float(threshold)) & ~failed & ~false_break
        return (~available) | pass_when_breakout

    def _confirmed_context_gate(self, df: pd.DataFrame) -> pd.Series:
        scfg = self.analyzer_config.get("sector_context", {})
        sector_available = _bool(df, "sector_context_available") & _bool(df, "sector_context_reliable")
        sector_weak = sector_available & (
            _num(df, "sector_market_rank") >= int(scfg.get("weak_sector_rank_min", 15))
        )
        persistence_low = _bool(df, "persistence_available") & df["leader_persistence_level"].astype(str).eq("LOW")
        emerging = df["leader_type"].astype(str).eq("EMERGING_LEADER")
        return ~(sector_weak & persistence_low & ~emerging)

    def _strong_context_gate(self, df: pd.DataFrame) -> pd.Series:
        scfg = self.analyzer_config.get("sector_context", {})
        sector_available = _bool(df, "sector_context_available") & _bool(df, "sector_context_reliable")
        persistence_available = _bool(df, "persistence_available")
        context_available = sector_available | persistence_available
        sector_support = (
            sector_available
            & _num(df, "sector_market_rank").between(1, int(scfg.get("strong_sector_rank_max", 5)))
            & _num(df, "sector_leader_rank").between(1, int(scfg.get("strong_sector_leader_rank_max", 3)))
        )
        persistent_support = persistence_available & df["leader_persistence_level"].astype(str).eq("HIGH")
        emerging_support = df["leader_type"].astype(str).eq("EMERGING_LEADER")
        return (~context_available) | sector_support | persistent_support | emerging_support

    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        leader = _num(df, "leader_score")
        timing = _num(df, "timing_score")
        chase = _num(df, "chase_risk")
        if self.phase == "confirmed":
            base = (
                (leader >= float(params["confirmed_leader"]))
                & (timing >= float(params["confirmed_timing"]))
                & (chase < float(params["max_chase_risk"]))
            )
            return base & self._quality_gate(df, float(params["min_breakout_quality"])) & self._confirmed_context_gate(df)

        base = (
            (leader >= float(params["strong_leader"]))
            & (timing >= float(params["strong_timing"]))
            & (chase < float(params["max_chase_risk"]))
            & (_num(df, "market_leader_rank") <= int(params["strong_rank_max"]))
        )
        return base & self._quality_gate(df, float(params["min_breakout_quality"])) & self._strong_context_gate(df)

    def validate_parameters(self, params: dict[str, Any]) -> bool:
        if self.phase != "strong" or not self.confirmed_floor:
            return True
        return (
            float(params["strong_leader"]) >= float(self.confirmed_floor.get("confirmed_leader", 0))
            and float(params["strong_timing"]) >= float(self.confirmed_floor.get("confirmed_timing", 0))
            and float(params["min_breakout_quality"]) >= float(self.confirmed_floor.get("min_breakout_quality", 0))
            and float(params["max_chase_risk"]) == float(self.confirmed_floor.get("max_chase_risk", params["max_chase_risk"]))
        )

    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.phase == "confirmed":
            return {
                "thresholds": {
                    "confirmed_leader": float(params["confirmed_leader"]),
                    "confirmed_timing": float(params["confirmed_timing"]),
                    "max_confirmed_chase_risk": float(params["max_chase_risk"]),
                },
                "breakout_quality": {
                    "confirmation": {
                        "min_confirmed_quality": float(params["min_breakout_quality"]),
                    }
                },
            }
        return {
            "thresholds": {
                "strong_confirmed_leader": float(params["strong_leader"]),
                "strong_confirmed_timing": float(params["strong_timing"]),
                "max_confirmed_chase_risk": float(params["max_chase_risk"]),
                "strong_rank_max": int(params["strong_rank_max"]),
            },
            "breakout_quality": {
                "confirmation": {
                    "min_strong_quality": float(params["min_breakout_quality"]),
                }
            },
        }
