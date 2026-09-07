from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


def _as_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _num(value: Any, default: float = np.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


@dataclass(frozen=True)
class LeadershipValidationConfig:
    retention_horizon: int = 5
    persistence_horizon: int = 10
    market_top_rank: int = 20
    trading_value_top_rank: int = 20
    false_leader_consecutive_days: int = 3
    false_leader_rank_min: int = 50
    false_leader_score_max: float = 60.0
    sector_min_available_days: int = 2


class LeadershipValidationEngine:
    """Build future-only labels for validating market leadership detection.

    The engine is intentionally post-hoc. It must never feed same-day screening.
    Labels are derived from later *scan dates* in the completed Range frame, not
    from future price returns.

    `leader_retention_5d` uses the independent Lifecycle Core definition
    (Leader Score >= lifecycle.leader_min_leader_score and Market Leader Rank <=
    lifecycle.leader_rank_max), so the threshold optimizer is not trained against
    its own CONFIRMED threshold.
    """

    def __init__(self, cfg: dict):
        raw = cfg.get("leadership_validation", {})
        self.cfg = LeadershipValidationConfig(
            retention_horizon=max(1, int(raw.get("retention_horizon", 5))),
            persistence_horizon=max(1, int(raw.get("persistence_horizon", 10))),
            market_top_rank=max(1, int(raw.get("market_top_rank", 20))),
            trading_value_top_rank=max(1, int(raw.get("trading_value_top_rank", 20))),
            false_leader_consecutive_days=max(1, int(raw.get("false_leader_consecutive_days", 3))),
            false_leader_rank_min=max(1, int(raw.get("false_leader_rank_min", 50))),
            false_leader_score_max=float(raw.get("false_leader_score_max", 60.0)),
            sector_min_available_days=max(1, int(raw.get("sector_min_available_days", 2))),
        )
        lifecycle = cfg.get("lifecycle", {})
        sector = cfg.get("sector_context", {})
        self.core_leader_score = float(lifecycle.get("leader_min_leader_score", 75.0))
        self.core_market_rank = int(lifecycle.get("leader_rank_max", 20))
        self.sector_market_rank_max = int(sector.get("strong_sector_rank_max", 5))
        self.sector_leader_rank_max = int(sector.get("strong_sector_leader_rank_max", 3))

    @staticmethod
    def _parse_dates(frame: pd.DataFrame) -> pd.Series:
        raw = frame.get("scan_date", pd.Series(index=frame.index, dtype=str)).astype(str).str.strip()
        ymd = pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
        fallback = pd.to_datetime(raw, errors="coerce")
        return ymd.fillna(fallback).dt.normalize()

    @staticmethod
    def _ticker_series(frame: pd.DataFrame) -> pd.Series:
        return frame.get("ticker", pd.Series(index=frame.index, dtype=str)).astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)

    @staticmethod
    def _three_consecutive(flags: list[bool], required: int) -> bool:
        streak = 0
        for flag in flags:
            streak = streak + 1 if flag else 0
            if streak >= required:
                return True
        return False

    def annotate(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            return frame.copy() if frame is not None else pd.DataFrame()
        if "scan_date" not in frame.columns or "ticker" not in frame.columns:
            raise ValueError("leadership validation requires scan_date and ticker columns")

        out = frame.copy()
        out["_lv_date"] = self._parse_dates(out)
        out["_lv_ticker"] = self._ticker_series(out)
        valid_dates = out["_lv_date"].dropna().drop_duplicates().sort_values().tolist()
        date_pos = {pd.Timestamp(d): i for i, d in enumerate(valid_dates)}

        # One row per ticker/date is expected. If duplicates exist, keep the last
        # row deterministically for future lookup while preserving all source rows.
        lookup: dict[tuple[pd.Timestamp, str], int] = {}
        for idx, row in out[["_lv_date", "_lv_ticker"]].iterrows():
            dt = row["_lv_date"]
            if pd.isna(dt):
                continue
            lookup[(pd.Timestamp(dt), str(row["_lv_ticker"]))] = idx

        cols: dict[str, list[Any]] = {
            "leadership_valid_5d": [],
            "leadership_valid_10d": [],
            "future_observed_days_5d": [],
            "future_observed_days_10d": [],
            "leader_retention_5d": [],
            "market_top20_retention_5d": [],
            "turnover_top20_retention_5d": [],
            "persistence_conversion_10d": [],
            "sector_leader_retention_5d": [],
            "sector_context_future_coverage_5d": [],
            "false_leader_5d": [],
            "leadership_quality_score": [],
        }

        h5 = self.cfg.retention_horizon
        h10 = self.cfg.persistence_horizon

        for _, base in out.iterrows():
            dt = base["_lv_date"]
            ticker = str(base["_lv_ticker"])
            if pd.isna(dt) or pd.Timestamp(dt) not in date_pos:
                for values in cols.values():
                    values.append(np.nan)
                continue

            pos = date_pos[pd.Timestamp(dt)]
            future5 = valid_dates[pos + 1 : pos + 1 + h5]
            future10 = valid_dates[pos + 1 : pos + 1 + h10]
            valid5 = len(future5) == h5
            valid10 = len(future10) == h10
            cols["leadership_valid_5d"].append(bool(valid5))
            cols["leadership_valid_10d"].append(bool(valid10))

            if not valid5:
                cols["future_observed_days_5d"].append(np.nan)
                cols["future_observed_days_10d"].append(np.nan if not valid10 else 0)
                for name in (
                    "leader_retention_5d",
                    "market_top20_retention_5d",
                    "turnover_top20_retention_5d",
                    "sector_leader_retention_5d",
                    "sector_context_future_coverage_5d",
                    "false_leader_5d",
                    "leadership_quality_score",
                ):
                    cols[name].append(np.nan)
                if valid10:
                    future_rows10 = [lookup.get((pd.Timestamp(d), ticker)) for d in future10]
                    observed10 = [idx for idx in future_rows10 if idx is not None]
                    cols["future_observed_days_10d"][-1] = len(observed10)
                    persistent = any(
                        str(out.at[idx, "leader_persistence_level"]).upper() == "HIGH"
                        or str(out.at[idx, "lifecycle_state"]).upper() == "PERSISTENT_LEADER"
                        for idx in observed10
                    ) if observed10 else False
                    cols["persistence_conversion_10d"].append(bool(persistent))
                else:
                    cols["persistence_conversion_10d"].append(np.nan)
                continue

            future_rows5 = [lookup.get((pd.Timestamp(d), ticker)) for d in future5]
            observed5 = [idx for idx in future_rows5 if idx is not None]
            cols["future_observed_days_5d"].append(len(observed5))

            leader_flags: list[bool] = []
            market_flags: list[bool] = []
            turnover_flags: list[bool] = []
            failure_flags: list[bool] = []
            sector_flags: list[bool] = []

            for idx in future_rows5:
                if idx is None:
                    leader_flags.append(False)
                    market_flags.append(False)
                    turnover_flags.append(False)
                    failure_flags.append(True)
                    continue

                row = out.loc[idx]
                leader_score = _num(row.get("leader_score"))
                market_rank = _num(row.get("market_leader_rank"))
                turnover_rank = _num(row.get("trading_value_rank"))
                persistence = str(row.get("leader_persistence_level", "UNKNOWN")).upper()

                leader_flags.append(
                    np.isfinite(leader_score)
                    and leader_score >= self.core_leader_score
                    and np.isfinite(market_rank)
                    and market_rank <= self.core_market_rank
                )
                market_flags.append(np.isfinite(market_rank) and market_rank <= self.cfg.market_top_rank)
                turnover_flags.append(
                    np.isfinite(turnover_rank) and turnover_rank <= self.cfg.trading_value_top_rank
                )
                failure_flags.append(
                    (not np.isfinite(market_rank) or market_rank > self.cfg.false_leader_rank_min)
                    and (not np.isfinite(leader_score) or leader_score < self.cfg.false_leader_score_max)
                    and persistence in {"LOW", "UNKNOWN", "NAN", ""}
                )

                reliable = _as_bool(row.get("sector_context_reliable", False))
                if reliable:
                    sector_market_rank = _num(row.get("sector_market_rank"))
                    sector_leader_rank = _num(row.get("sector_leader_rank"))
                    sector_flags.append(
                        np.isfinite(sector_market_rank)
                        and sector_market_rank <= self.sector_market_rank_max
                        and np.isfinite(sector_leader_rank)
                        and sector_leader_rank <= self.sector_leader_rank_max
                    )

            leader_ret = float(np.mean(leader_flags) * 100.0)
            market_ret = float(np.mean(market_flags) * 100.0)
            turnover_ret = float(np.mean(turnover_flags) * 100.0)
            sector_coverage = len(sector_flags) / h5
            sector_ret = (
                float(np.mean(sector_flags) * 100.0)
                if len(sector_flags) >= self.cfg.sector_min_available_days
                else np.nan
            )
            false_leader = self._three_consecutive(
                failure_flags,
                self.cfg.false_leader_consecutive_days,
            )

            cols["leader_retention_5d"].append(leader_ret)
            cols["market_top20_retention_5d"].append(market_ret)
            cols["turnover_top20_retention_5d"].append(turnover_ret)
            cols["sector_leader_retention_5d"].append(sector_ret)
            cols["sector_context_future_coverage_5d"].append(round(sector_coverage, 4))
            cols["false_leader_5d"].append(bool(false_leader))

            if valid10:
                future_rows10 = [lookup.get((pd.Timestamp(d), ticker)) for d in future10]
                observed10 = [idx for idx in future_rows10 if idx is not None]
                cols["future_observed_days_10d"].append(len(observed10))
                persistent = any(
                    str(out.at[idx, "leader_persistence_level"]).upper() == "HIGH"
                    or str(out.at[idx, "lifecycle_state"]).upper() == "PERSISTENT_LEADER"
                    for idx in observed10
                ) if observed10 else False
                cols["persistence_conversion_10d"].append(bool(persistent))
            else:
                cols["future_observed_days_10d"].append(np.nan)
                cols["persistence_conversion_10d"].append(np.nan)

            # Diagnostic composite only. The optimizer scores each component
            # separately and re-normalizes when sector data is unavailable.
            components = [
                (0.30, leader_ret),
                (0.20, market_ret),
                (0.15, turnover_ret),
                (0.10, 0.0 if false_leader else 100.0),
            ]
            persistent_value = cols["persistence_conversion_10d"][-1]
            if pd.notna(persistent_value):
                components.append((0.15, 100.0 if bool(persistent_value) else 0.0))
            if pd.notna(sector_ret):
                components.append((0.10, float(sector_ret)))
            total_weight = sum(weight for weight, _ in components)
            quality = sum(weight * value for weight, value in components) / total_weight if total_weight else np.nan
            cols["leadership_quality_score"].append(round(float(quality), 4) if pd.notna(quality) else np.nan)

        for name, values in cols.items():
            out[name] = values

        return out.drop(columns=["_lv_date", "_lv_ticker"], errors="ignore")

    def summary(self, frame: pd.DataFrame, group_col: str | None = None) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        groups = [("ALL", frame)] if group_col is None or group_col not in frame.columns else list(frame.groupby(group_col, dropna=False))
        rows: list[dict[str, Any]] = []
        for label, grp in groups:
            valid = grp[grp.get("leadership_valid_10d", False).fillna(False).astype(bool)].copy()
            false_series = valid.get("false_leader_5d", pd.Series(index=valid.index, dtype=float))
            false_numeric = false_series.map(lambda x: 1.0 if _as_bool(x) else 0.0) if not false_series.empty else pd.Series(dtype=float)
            persistence_series = valid.get("persistence_conversion_10d", pd.Series(index=valid.index, dtype=float))
            persistence_numeric = persistence_series.map(lambda x: 1.0 if _as_bool(x) else 0.0) if not persistence_series.empty else pd.Series(dtype=float)
            rows.append(
                {
                    "group": str(label),
                    "count": int(len(valid)),
                    "unique_dates": int(pd.to_datetime(valid.get("scan_date"), errors="coerce").nunique()) if not valid.empty else 0,
                    "avg_leader_retention_5d": pd.to_numeric(valid.get("leader_retention_5d"), errors="coerce").mean(),
                    "avg_market_top20_retention_5d": pd.to_numeric(valid.get("market_top20_retention_5d"), errors="coerce").mean(),
                    "avg_turnover_top20_retention_5d": pd.to_numeric(valid.get("turnover_top20_retention_5d"), errors="coerce").mean(),
                    "persistence_conversion_10d_rate": persistence_numeric.mean() * 100.0 if not persistence_numeric.empty else np.nan,
                    "avg_sector_leader_retention_5d": pd.to_numeric(valid.get("sector_leader_retention_5d"), errors="coerce").mean(),
                    "false_leader_5d_rate": false_numeric.mean() * 100.0 if not false_numeric.empty else np.nan,
                    "avg_leadership_quality_score": pd.to_numeric(valid.get("leadership_quality_score"), errors="coerce").mean(),
                    "avg_D+20_diagnostic": pd.to_numeric(valid.get("D+20"), errors="coerce").mean() if "D+20" in valid.columns else np.nan,
                }
            )
        return pd.DataFrame(rows)
