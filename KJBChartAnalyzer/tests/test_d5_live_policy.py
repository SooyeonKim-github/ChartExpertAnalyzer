from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

KJB_ROOT = Path(__file__).resolve().parents[1]
if str(KJB_ROOT) not in sys.path:
    sys.path.insert(0, str(KJB_ROOT))

from chartsel.selection.d5_live import apply_live_d5_policy


def _cfg() -> dict:
    return {
        "d5_v2": {
            "enabled_for_live": True,
            "selection_weight": 0.45,
            "timing_weight": 0.55,
            "selection_min": 70,
            "timing_min": 72,
            "d5_score_min": 70,
            "overextension_max_exclusive": 8,
            "rs_hard": 92,
            "leader_soft": 80,
            "leader_hard": 88,
            "sector_soft": 78,
            "sector_hard": 86,
            "combo_rs_leader_penalty": 3,
            "combo_triple_penalty": 4,
            "daily_top_n": 3,
        }
    }


def _row(ticker: str, selection: float, timing: float, *, rs: float = 80, leader: float = 70, sector: float = 70):
    return {
        "ticker": ticker,
        "asof": "2026-09-08",
        "Status": "CONFIRMED",
        "score": selection,
        "raw_selection_score": selection,
        "d5_score": selection,
        "overextension_penalty": 0.0,
        "timing_score": timing,
        "risk_score": 20,
        "relative_strength_score": rs,
        "leader_score": leader,
        "sector_leader_score": sector,
    }


def test_final_policy_keeps_only_daily_top3_operational_confirmed() -> None:
    frame = pd.DataFrame([
        _row("000001", 82, 82),
        _row("000002", 80, 80),
        _row("000003", 78, 78),
        _row("000004", 76, 76),
    ])
    out = apply_live_d5_policy(frame, _cfg())

    assert int(out["D5_Status"].eq("D5_CONFIRMED").sum()) == 4
    assert int(out["Status"].eq("CONFIRMED").sum()) == 3
    confirmed = out[out["Status"].eq("CONFIRMED")]
    assert confirmed["D5_Selected"].all()
    assert set(confirmed["ticker"]) == {"000001", "000002", "000003"}
    assert out.loc[out["ticker"].eq("000004"), "Status"].iloc[0] == "WATCH"


def test_overextended_baseline_confirmed_is_demoted() -> None:
    normal = _row("000001", 80, 80)
    hot = _row("000002", 90, 90, rs=95, leader=90, sector=90)
    frame = pd.DataFrame([normal, hot])

    out = apply_live_d5_policy(frame, _cfg())
    hot_row = out[out["ticker"].eq("000002")].iloc[0]

    assert hot_row["Baseline_Status"] == "CONFIRMED"
    assert hot_row["overextension_penalty"] >= 8
    assert hot_row["D5_Status"] == "D5_WATCH"
    assert hot_row["Status"] == "WATCH"


def test_baseline_watch_is_never_promoted() -> None:
    row = _row("000001", 90, 90)
    row["Status"] = "WATCH"
    frame = pd.DataFrame([row])

    out = apply_live_d5_policy(frame, _cfg())
    assert out.iloc[0]["Baseline_Status"] == "WATCH"
    assert out.iloc[0]["D5_Status"] == "D5_WATCH"
    assert out.iloc[0]["Status"] == "WATCH"
