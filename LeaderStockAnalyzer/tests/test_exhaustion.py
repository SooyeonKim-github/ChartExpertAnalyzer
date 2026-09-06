from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd

from leader_stock_analyzer.analyzer import LeaderStockAnalyzer
from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.exhaustion import ExhaustionRiskEngine, ExhaustionTransitionAnalyzer
from leader_stock_analyzer.leadership_history import LeadershipHistoryContext


def _frame(close, trading_value):
    close = np.asarray(close, dtype=float)
    tv = np.asarray(trading_value, dtype=float)
    volume = np.divide(tv, close, out=np.zeros_like(tv), where=close > 0)
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.015,
            "low": close * 0.985,
            "close": close,
            "volume": volume,
            "trading_value": tv,
        },
        index=pd.date_range("2026-06-01", periods=len(close), freq="B"),
    )


def _item(cfg, daily, *, ticker="999999"):
    analyzer = LeaderStockAnalyzer(cfg)
    item = analyzer.analyze_one(
        scan_date=daily.index[-1].strftime("%Y%m%d"),
        ticker=ticker,
        name="TEST",
        market="KOSPI",
        price=float(daily.iloc[-1]["close"]),
        return_pct=(float(daily.iloc[-1]["close"]) / float(daily.iloc[-2]["close"]) - 1) * 100,
        trading_value=float(daily.iloc[-1]["trading_value"]),
        trading_value_rank=5,
        universe_size=100,
        daily=daily,
        intraday=pd.DataFrame(),
        market_return_pct=0.0,
    )
    return replace(
        item,
        leader_score=85.0,
        market_leader_rank=5,
        persistence_available=True,
        leader_persistence_score=75.0,
        leader_persistence_level="HIGH",
        turnover_top20_days_5d=5,
        chase_risk=20.0,
    )


def test_exhaustion_risk_keeps_healthy_leader_below_high():
    cfg = deepcopy(DEFAULT_CONFIG)
    close = np.linspace(100, 120, 40)
    tv = np.linspace(80, 100, 40) * 1_000_000_000.0
    daily = _frame(close, tv)
    history = LeadershipHistoryContext.build({"999999": daily}, scan_date=daily.index[-1])
    item = _item(cfg, daily)

    out = ExhaustionRiskEngine(cfg).enrich(
        [item], daily_by_ticker={"999999": daily}, history=history
    )[0]

    assert out.exhaustion_risk_available is True
    assert out.exhaustion_risk_score is not None
    assert out.exhaustion_risk_score < cfg["exhaustion_risk"]["high_score"]
    assert out.exhaustion_risk_label in {"LOW", "WATCH"}


def test_exhaustion_risk_detects_overheated_distribution():
    cfg = deepcopy(DEFAULT_CONFIG)
    close = np.array(
        [100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
         110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
         120, 122, 125, 129, 134, 140, 148, 158, 169, 181,
         194, 205, 213, 218, 220, 221, 218, 213, 207, 201],
        dtype=float,
    )
    tv = np.array(
        [50] * 25 + [80, 120, 180, 260, 350, 420, 380, 300, 230, 170, 120, 90, 70, 55, 45],
        dtype=float,
    ) * 1_000_000_000.0
    daily = _frame(close, tv)

    # Add other candidates so rank reversal can be measured cross-sectionally.
    frames = {"999999": daily}
    for idx in range(1, 25):
        frames[f"{idx:06d}"] = _frame(
            np.linspace(100, 102, len(close)),
            np.full(len(close), idx * 20_000_000_000.0),
        )
    history = LeadershipHistoryContext.build(frames, scan_date=daily.index[-1])
    item = replace(
        _item(cfg, daily),
        chase_risk=75.0,
        false_breakout_flag=True,
        breakout_exhaustion_risk=True,
        upper_wick_ratio=0.65,
        close_location_value=0.20,
        emerging_rs_acceleration=-8.0,
        rank_acceleration=-12.0,
        leader_persistence_score=35.0,
        leader_persistence_level="LOW",
    )

    out = ExhaustionRiskEngine(cfg).enrich(
        [item], daily_by_ticker={"999999": daily}, history=history
    )[0]

    assert out.exhaustion_risk_score is not None
    assert out.exhaustion_risk_score >= cfg["exhaustion_risk"]["high_score"]
    assert out.exhaustion_risk_label in {"HIGH", "CRITICAL"}
    assert out.exhaustion_distribution_score > 0
    assert out.exhaustion_deceleration_score > 0
    assert "false_breakout" in out.exhaustion_flags


def test_exhaustion_report_deduplicates_episode_and_tracks_breakdown():
    cfg = deepcopy(DEFAULT_CONFIG)
    df = pd.DataFrame(
        [
            {
                "ticker": "111111",
                "scan_date": "20260820",
                "lifecycle_state": "LEADER",
                "exhaustion_risk_label": "LOW",
                "D+20": 4.0,
            },
            {
                "ticker": "111111",
                "scan_date": "20260821",
                "lifecycle_state": "LEADER",
                "exhaustion_risk_label": "HIGH",
                "D+5": -2.0,
                "D+20": -8.0,
                "D+60": -15.0,
                "MFE_D20": 3.0,
                "MAE_D20": -12.0,
            },
            {
                "ticker": "111111",
                "scan_date": "20260824",
                "lifecycle_state": "LEADER",
                "exhaustion_risk_label": "HIGH",
            },
            {
                "ticker": "111111",
                "scan_date": "20260825",
                "lifecycle_state": "EXHAUSTING",
                "exhaustion_risk_label": "CRITICAL",
            },
            {
                "ticker": "111111",
                "scan_date": "20260826",
                "lifecycle_state": "BROKEN",
                "exhaustion_risk_label": "CRITICAL",
            },
        ]
    )

    report = ExhaustionTransitionAnalyzer(cfg)
    events = report.events(df)
    summary = report.summary(events)

    assert len(events) == 1
    event = events.iloc[0]
    assert event["exhaustion_event_label"] == "HIGH"
    assert bool(event["exhausting_within_3d"]) is True
    assert bool(event["broken_within_5d"]) is True
    assert summary.iloc[0]["event_count"] == 1
    assert summary.iloc[0]["avg_D+20"] == -8.0
    assert summary.iloc[0]["avg_MAE_D20"] == -12.0
