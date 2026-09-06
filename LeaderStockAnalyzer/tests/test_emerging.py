from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd

from leader_stock_analyzer.analyzer import LeaderStockAnalyzer
from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.emerging import EmergingLeaderEngine, EmergingTransitionAnalyzer
from leader_stock_analyzer.leadership_history import LeadershipHistoryContext
from leader_stock_analyzer.lifecycle import LeaderLifecycleEngine


def _frame(close, trading_value):
    close = np.asarray(close, dtype=float)
    tv = np.asarray(trading_value, dtype=float)
    volume = np.divide(tv, close, out=np.zeros_like(tv), where=close > 0)
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
            "trading_value": tv,
        },
        index=pd.date_range("2026-08-03", periods=len(close), freq="B"),
    )


def _base_item(cfg, daily, *, return_pct: float = 4.0, chase_risk: float = 20.0):
    analyzer = LeaderStockAnalyzer(cfg)
    item = analyzer.analyze_one(
        scan_date="20260814",
        ticker="999999",
        name="RISING",
        market="KOSPI",
        price=float(daily.iloc[-1]["close"]),
        return_pct=return_pct,
        trading_value=float(daily.iloc[-1]["trading_value"]),
        trading_value_rank=3,
        universe_size=100,
        daily=daily,
        intraday=pd.DataFrame(),
        market_return_pct=0.0,
    )
    return replace(
        item,
        leader_score=80.0,
        market_leader_rank=3,
        return_pct=return_pct,
        chase_risk=chase_risk,
        breakout_exhaustion_risk=False,
        false_breakout_flag=False,
        persistence_available=True,
        leader_persistence_score=40.0,
        leader_persistence_level="LOW",
        turnover_top20_days_5d=2,
    )


def _history_fixture():
    dates = 10
    frames = {}
    for idx in range(1, 41):
        frames[f"{idx:06d}"] = _frame(
            np.linspace(100, 101, dates),
            np.full(dates, idx * 1_000_000_000.0),
        )

    rising = _frame(
        np.array([100, 100, 100, 100, 100, 101, 102, 104, 107, 111], dtype=float),
        np.array([3, 4, 5, 6, 8, 10, 15, 22, 30, 38], dtype=float) * 1_000_000_000.0,
    )
    frames["999999"] = rising
    return rising, LeadershipHistoryContext.build(frames, scan_date="20260814")


def test_emerging_engine_detects_quality_rank_velocity():
    cfg = deepcopy(DEFAULT_CONFIG)
    rising, history = _history_fixture()
    item = _base_item(cfg, rising)

    out = EmergingLeaderEngine(cfg).enrich(
        [item],
        history=history,
        market_period_returns={"KOSPI": {3: 0.0, 5: 0.0}},
    )[0]

    assert out.emerging_available is True
    assert out.emerging_rank_today <= 5
    assert out.rank_velocity_5d is not None and out.rank_velocity_5d >= 30
    assert out.emerging_rs_acceleration is not None and out.emerging_rs_acceleration > 0
    assert out.emerging_raw_score is not None
    assert out.emerging_leader_score is not None and out.emerging_leader_score >= 70
    assert out.momentum_spike_flag is False
    assert out.true_emerging_flag is True


def test_emerging_engine_separates_momentum_spike():
    cfg = deepcopy(DEFAULT_CONFIG)
    rising, history = _history_fixture()
    item = _base_item(cfg, rising, return_pct=18.0, chase_risk=45.0)

    out = EmergingLeaderEngine(cfg).enrich(
        [item],
        history=history,
        market_period_returns={"KOSPI": {3: 0.0, 5: 0.0}},
    )[0]

    assert out.emerging_raw_score is not None
    assert out.emerging_overheat_penalty > 0
    assert out.momentum_spike_flag is True
    assert out.emerging_label == "MOMENTUM_SPIKE"
    assert out.true_emerging_flag is False
    assert "high_chase_risk" in out.emerging_overheat_flags


def test_lifecycle_requires_two_day_emerging_confirmation_by_default():
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["lifecycle"]["promotion_confirm_days"] = 2
    assert cfg["lifecycle"]["allow_strong_emerging_fast_track"] is False

    daily = _frame(np.linspace(100, 120, 30), np.full(30, 100_000_000_000.0))
    analyzer = LeaderStockAnalyzer(cfg)
    base = analyzer.analyze_one(
        scan_date="20260820",
        ticker="111111",
        name="A",
        market="KOSPI",
        price=float(daily.iloc[-1]["close"]),
        return_pct=1.0,
        trading_value=float(daily.iloc[-1]["trading_value"]),
        trading_value_rank=10,
        universe_size=100,
        daily=daily,
        intraday=pd.DataFrame(),
        market_return_pct=0.0,
    )
    engine = LeaderLifecycleEngine(cfg)

    day1 = engine.enrich(
        [
            replace(
                base,
                leader_score=65.0,
                market_leader_rank=30,
                emerging_available=True,
                true_emerging_flag=False,
            )
        ],
        {"111111": daily},
    )[0]
    assert day1.lifecycle_state == "DISCOVERY"

    candidate = replace(
        base,
        scan_date="20260821",
        leader_score=80.0,
        market_leader_rank=10,
        emerging_available=True,
        true_emerging_flag=True,
        strong_emerging_flag=True,
        persistence_available=True,
        leader_persistence_score=20.0,
        leader_persistence_level="LOW",
        turnover_top20_days_5d=1,
    )
    day2 = engine.enrich([candidate], {"111111": daily})[0]
    assert day2.lifecycle_state == "DISCOVERY"
    assert "pending_1/2" in day2.lifecycle_reason

    day3 = engine.enrich(
        [replace(candidate, scan_date="20260824")],
        {"111111": daily},
    )[0]
    assert day3.lifecycle_state == "EMERGING"
    assert day3.lifecycle_reason == "confirmed_rank_velocity_emerging"


def test_fast_track_can_be_explicitly_reenabled():
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["lifecycle"]["allow_strong_emerging_fast_track"] = True
    daily = _frame(np.linspace(100, 120, 30), np.full(30, 100_000_000_000.0))
    analyzer = LeaderStockAnalyzer(cfg)
    base = analyzer.analyze_one(
        scan_date="20260820",
        ticker="222222",
        name="B",
        market="KOSPI",
        price=float(daily.iloc[-1]["close"]),
        return_pct=1.0,
        trading_value=float(daily.iloc[-1]["trading_value"]),
        trading_value_rank=30,
        universe_size=100,
        daily=daily,
        intraday=pd.DataFrame(),
        market_return_pct=0.0,
    )
    engine = LeaderLifecycleEngine(cfg)
    day1 = engine.enrich(
        [replace(base, leader_score=65.0, market_leader_rank=30, emerging_available=True)],
        {"222222": daily},
    )[0]
    assert day1.lifecycle_state == "DISCOVERY"

    day2 = engine.enrich(
        [
            replace(
                base,
                scan_date="20260821",
                leader_score=80.0,
                market_leader_rank=10,
                emerging_available=True,
                true_emerging_flag=True,
                strong_emerging_flag=True,
                persistence_available=True,
                leader_persistence_score=20.0,
                leader_persistence_level="LOW",
                turnover_top20_days_5d=1,
            )
        ],
        {"222222": daily},
    )[0]
    assert day2.lifecycle_state == "EMERGING"
    assert day2.lifecycle_reason == "strong_emerging_fast_track"


def test_emerging_summary_splits_cohorts():
    cfg = deepcopy(DEFAULT_CONFIG)
    df = pd.DataFrame(
        [
            {
                "ticker": "111111",
                "scan_date": "20260820",
                "true_emerging_flag": True,
                "lifecycle_state": "EMERGING",
                "lifecycle_prev_state": "UNKNOWN",
                "lifecycle_days_in_state": 1,
                "lifecycle_reason": "initial_emerging_evidence",
                "D+5": 2.0,
                "D+20": 5.0,
            },
            {
                "ticker": "111111",
                "scan_date": "20260821",
                "true_emerging_flag": True,
                "lifecycle_state": "EMERGING",
                "lifecycle_prev_state": "EMERGING",
                "lifecycle_days_in_state": 2,
                "lifecycle_reason": "emerging_conditions_held",
                "D+5": 1.0,
                "D+20": 3.0,
            },
            {
                "ticker": "222222",
                "scan_date": "20260820",
                "true_emerging_flag": False,
                "lifecycle_state": "DISCOVERY",
                "lifecycle_prev_state": "UNKNOWN",
                "lifecycle_days_in_state": 1,
                "lifecycle_reason": "initial_discovery_evidence",
            },
            {
                "ticker": "222222",
                "scan_date": "20260821",
                "true_emerging_flag": True,
                "lifecycle_state": "EMERGING",
                "lifecycle_prev_state": "DISCOVERY",
                "lifecycle_days_in_state": 1,
                "lifecycle_reason": "confirmed_rank_velocity_emerging",
                "D+5": 3.0,
                "D+20": 7.0,
            },
            {
                "ticker": "222222",
                "scan_date": "20260822",
                "true_emerging_flag": False,
                "lifecycle_state": "LEADER",
                "lifecycle_prev_state": "EMERGING",
                "lifecycle_days_in_state": 1,
                "lifecycle_reason": "confirmed_emerging_to_leader",
            },
        ]
    )

    reporter = EmergingTransitionAnalyzer(cfg)
    events = reporter.events(df)
    summary = reporter.summary(events)

    assert len(events) == 2
    assert set(events["event_type"]) == {"INITIAL_INFERENCE", "RANK_VELOCITY_CONFIRMED"}
    assert set(summary["cohort"]) == {"ALL", "INITIAL_INFERENCE", "RANK_VELOCITY_CONFIRMED"}
    rank_row = summary[summary["cohort"].eq("RANK_VELOCITY_CONFIRMED")].iloc[0]
    assert rank_row["event_count"] == 1
    assert rank_row["leader_within_3d_rate"] == 100.0
