from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd

from leader_stock_analyzer.analyzer import LeaderStockAnalyzer
from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.emerging import EmergingLeaderEngine
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


def _base_item(cfg, daily):
    analyzer = LeaderStockAnalyzer(cfg)
    item = analyzer.analyze_one(
        scan_date="20260814",
        ticker="999999",
        name="RISING",
        market="KOSPI",
        price=float(daily.iloc[-1]["close"]),
        return_pct=4.0,
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
        chase_risk=20.0,
        breakout_exhaustion_risk=False,
        false_breakout_flag=False,
        persistence_available=True,
        leader_persistence_score=40.0,
        leader_persistence_level="LOW",
        turnover_top20_days_5d=2,
    )


def test_emerging_engine_detects_fast_rank_velocity():
    cfg = deepcopy(DEFAULT_CONFIG)
    dates = 10
    frames = {}
    for idx in range(1, 41):
        frames[f"{idx:06d}"] = _frame(
            np.linspace(100, 101, dates),
            np.full(dates, idx * 1_000_000_000.0),
        )

    rising = _frame(
        np.linspace(100, 125, dates),
        np.array([3, 4, 5, 6, 8, 10, 15, 22, 30, 38], dtype=float) * 1_000_000_000.0,
    )
    frames["999999"] = rising
    history = LeadershipHistoryContext.build(frames, scan_date="20260814")
    item = _base_item(cfg, rising)

    out = EmergingLeaderEngine(cfg).enrich(
        [item],
        history=history,
        market_period_returns={"KOSPI": {3: 0.0, 5: 0.0}},
    )[0]

    assert out.emerging_available is True
    assert out.emerging_rank_today <= 5
    assert out.rank_velocity_5d is not None and out.rank_velocity_5d >= 30
    assert out.emerging_leader_score is not None and out.emerging_leader_score >= 70
    assert out.true_emerging_flag is True
    assert out.strong_emerging_flag is True


def test_lifecycle_requires_emerging_feature_when_available():
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["lifecycle"]["promotion_confirm_days"] = 2
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

    discovery = replace(
        base,
        leader_score=65.0,
        market_leader_rank=30,
        emerging_available=True,
        true_emerging_flag=False,
        persistence_available=True,
        leader_persistence_score=20.0,
        leader_persistence_level="LOW",
        turnover_top20_days_5d=0,
    )
    day1 = engine.enrich([discovery], {"111111": daily})[0]
    assert day1.lifecycle_state == "DISCOVERY"

    strong_but_not_emerging = replace(
        discovery,
        scan_date="20260821",
        leader_score=80.0,
        market_leader_rank=10,
        turnover_top20_days_5d=2,
        true_emerging_flag=False,
    )
    day2 = engine.enrich([strong_but_not_emerging], {"111111": daily})[0]
    assert day2.lifecycle_state == "DISCOVERY"

    emerging = replace(
        strong_but_not_emerging,
        scan_date="20260824",
        true_emerging_flag=True,
    )
    day3 = engine.enrich([emerging], {"111111": daily})[0]
    assert day3.lifecycle_state == "DISCOVERY"
    assert "pending_1/2" in day3.lifecycle_reason

    day4 = engine.enrich(
        [replace(emerging, scan_date="20260825")],
        {"111111": daily},
    )[0]
    assert day4.lifecycle_state == "EMERGING"
    assert day4.lifecycle_reason == "confirmed_rank_velocity_emerging"


def test_strong_emerging_fast_tracks_discovery():
    cfg = deepcopy(DEFAULT_CONFIG)
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
