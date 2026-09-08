from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from d5_diagnostics import build_d5_strategy
from ..sector.sector_service import SectorBacktestService
from ..sector.sector_strength import sector_leader_score


def _num(frame: pd.DataFrame, column: str, default=np.nan) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def attach_live_sector_context(
    table: pd.DataFrame,
    *,
    price_cache: dict[str, pd.DataFrame],
    benchmark_cache: dict[str, pd.DataFrame | None],
    sector_mapping_excel: str | Path,
    cfg: dict,
) -> pd.DataFrame:
    """Attach the same sector-leader context used by the range backtest.

    If sector aggregation cannot be built, the range implementation also falls back
    to Selection + Stock RS. Live screening follows the same fallback instead of
    aborting the entire KR screening workflow.
    """
    out = table.copy()
    if out.empty:
        return out

    sector_cfg = cfg.get("sector_strength", {}) or {}
    service = None
    build_error = ""
    try:
        service = SectorBacktestService(sector_mapping_excel, sector_cfg)
        service.build(
            price_cache,
            benchmark_cache,
            allowed_tickers=set(price_cache),
        )
    except Exception as exc:
        build_error = str(exc)
        service = None

    sector_names: list[str] = []
    sector_composite: list[float] = []
    sector_rs: list[float] = []
    sector_flow: list[float] = []
    scopes: list[str] = []
    leader_scores: list[float] = []
    selection_weights: list[float] = []
    stock_rs_weights: list[float] = []
    sector_weights: list[float] = []

    for _, row in out.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        market = str(row.get("market", "KOSPI"))
        asof = pd.to_datetime(row.get("asof"), errors="coerce")
        if pd.isna(asof):
            asof = pd.Timestamp.today().normalize()

        if service is not None:
            context = service.context(ticker, asof, fallback_market=market)
        else:
            context = {
                "sector_name": "기타/미분류",
                "sector_composite_score": np.nan,
                "sector_rs_score": np.nan,
                "sector_flow_score": np.nan,
                "sector_aggregation_scope": "none",
            }

        sector_value = pd.to_numeric(
            pd.Series([context.get("sector_composite_score")]), errors="coerce"
        ).iloc[0]
        sector_for_leader = None if pd.isna(sector_value) else float(sector_value)

        selection = float(pd.to_numeric(row.get("raw_selection_score", row.get("score", 0.0)), errors="coerce"))
        stock_rs = float(pd.to_numeric(row.get("relative_strength_score", 50.0), errors="coerce"))
        market_regime = str(row.get("market_regime", ""))
        leader, weights = sector_leader_score(
            selection,
            stock_rs,
            sector_for_leader,
            market_regime,
            sector_cfg,
        )

        sector_names.append(str(context.get("sector_name", "기타/미분류")))
        sector_composite.append(float(sector_value) if not pd.isna(sector_value) else np.nan)
        sector_rs.append(pd.to_numeric(context.get("sector_rs_score"), errors="coerce"))
        sector_flow.append(pd.to_numeric(context.get("sector_flow_score"), errors="coerce"))
        scopes.append(str(context.get("sector_aggregation_scope", "none")))
        leader_scores.append(leader)
        selection_weights.append(weights["selection"])
        stock_rs_weights.append(weights["stock_rs"])
        sector_weights.append(weights["sector"])

    out["sector_name"] = sector_names
    out["sector_composite_score"] = sector_composite
    out["sector_rs_score"] = sector_rs
    out["sector_flow_score"] = sector_flow
    out["sector_aggregation_scope"] = scopes
    out["sector_context_error"] = build_error
    out["sector_leader_score"] = leader_scores
    out["sector_leader_selection_weight"] = selection_weights
    out["sector_leader_stock_rs_weight"] = stock_rs_weights
    out["sector_leader_sector_weight"] = sector_weights
    return out


def apply_live_d5_policy(table: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Apply the finalized KJB D+5 baseline to a live screen table.

    Final live policy (frozen after walk-forward review):
    - baseline CONFIRMED is a prerequisite; WATCH is never promoted
    - Selection >= 70, Timing >= 72
    - Selection/Timing weight = 45/55
    - RS hard 92
    - Leader soft/hard 80/88
    - Sector Leader soft/hard 78/86
    - RS+Leader penalty 3, triple penalty 4
    - Overextension penalty < 8
    - D+5 adjusted score >= 70
    - operational CONFIRMED = D5_CONFIRMED daily Top 3
    - Market Regime is informational only; no hard/soft selection adjustment
    """
    out = table.copy()
    if out.empty:
        return out

    policy = cfg.get("d5_v2", {}) or {}
    if not bool(policy.get("enabled_for_live", False)):
        return out

    out["Baseline_Status"] = out.get("Status", pd.Series("WATCH", index=out.index)).astype(str)
    if "overextension_penalty" in out.columns:
        out["legacy_overextension_penalty"] = _num(out, "overextension_penalty")
    if "d5_score" in out.columns:
        out["legacy_d5_score"] = _num(out, "d5_score")

    out["selection_score"] = _num(out, "raw_selection_score")
    if out["selection_score"].isna().all():
        out["selection_score"] = _num(out, "score")
    out["signal_date"] = pd.to_datetime(out.get("asof"), errors="coerce").dt.normalize()

    scored = build_d5_strategy(
        out,
        selection_weight=float(policy.get("selection_weight", 0.45)),
        timing_weight=float(policy.get("timing_weight", 0.55)),
        rs_hard=float(policy.get("rs_hard", 92.0)),
        leader_soft=float(policy.get("leader_soft", 80.0)),
        leader_hard=float(policy.get("leader_hard", 88.0)),
        sector_soft=float(policy.get("sector_soft", 78.0)),
        sector_hard=float(policy.get("sector_hard", 86.0)),
        rs_leader_combo_penalty=float(policy.get("combo_rs_leader_penalty", 3.0)),
        triple_combo_penalty=float(policy.get("combo_triple_penalty", 4.0)),
        overextension_max_exclusive=float(policy.get("overextension_max_exclusive", 8.0)),
        selection_min=float(policy.get("selection_min", 70.0)),
        timing_min=float(policy.get("timing_min", 72.0)),
        d5_score_min=float(policy.get("d5_score_min", 70.0)),
    )

    top_n = int(policy.get("daily_top_n", 3))
    rank = _num(scored, "d5_confirmed_daily_rank")
    selected = scored["D5_Status"].eq("D5_CONFIRMED") & rank.le(top_n)
    scored["D5_Selected"] = selected
    scored["D5_DailyTopN"] = top_n
    scored["d5_policy_version"] = "KJB_D5_FINAL_V1"

    baseline = scored["Baseline_Status"].astype(str).str.upper()
    scored["Status"] = np.select(
        [selected, baseline.eq("REJECTED")],
        ["CONFIRMED", "REJECTED"],
        default="WATCH",
    )

    # Operational ranking/output uses the frozen D+5 adjusted score. Raw score remains
    # available in raw_selection_score for audit and later research.
    scored["score"] = _num(scored, "d5_adjusted_score")
    priority = scored["Status"].map({"CONFIRMED": 0, "WATCH": 1, "REJECTED": 2}).fillna(3)
    scored = (
        scored.assign(_status_priority=priority)
        .sort_values(
            ["_status_priority", "score", "timing_score", "sector_leader_score", "risk_score"],
            ascending=[True, False, False, False, True],
            na_position="last",
        )
        .drop(columns=["_status_priority"])
        .reset_index(drop=True)
    )
    return scored
