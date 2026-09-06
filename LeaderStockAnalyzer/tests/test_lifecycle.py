from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd

from leader_stock_analyzer.analyzer import LeaderStockAnalyzer
from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.lifecycle import LeaderLifecycleEngine


def _daily(last_drop: bool = False) -> pd.DataFrame:
    close = np.linspace(100.0, 120.0, 40)
    if last_drop:
        close[-1] = 90.0
    volume = np.full(40, 1_000_000.0)
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
            "trading_value": close * volume,
        },
        index=pd.date_range("2026-07-01", periods=40, freq="B"),
    )


def _base_result(cfg, daily: pd.DataFrame):
    analyzer = LeaderStockAnalyzer(cfg)
    item = analyzer.analyze_one(
        scan_date="20260825",
        ticker="111111",
        name="A",
        market="KOSPI",
        price=float(daily.iloc[-1]["close"]),
        return_pct=3.0,
        trading_value=float(daily.iloc[-1]["trading_value"]),
        trading_value_rank=5,
        universe_size=100,
        daily=daily,
        intraday=pd.DataFrame(),
        market_return_pct=0.0,
    )
    return replace(
        item,
        leader_score=82.0,
        market_leader_rank=5,
        persistence_available=True,
        leader_persistence_score=55.0,
        leader_persistence_level="MEDIUM",
        turnover_top20_days_5d=3,
        chase_risk=10.0,
        breakout_exhaustion_risk=False,
        false_breakout_flag=False,
    )


def test_lifecycle_initial_observation_can_infer_persistent_leader():
    cfg = deepcopy(DEFAULT_CONFIG)
    daily = _daily()
    item = replace(
        _base_result(cfg, daily),
        leader_score=88.0,
        leader_persistence_score=82.0,
        leader_persistence_level="HIGH",
        turnover_top20_days_5d=5,
    )

    out = LeaderLifecycleEngine(cfg).enrich([item], {"111111": daily})[0]

    assert out.lifecycle_available is True
    assert out.lifecycle_state == "PERSISTENT_LEADER"
    assert out.lifecycle_prev_state == "UNKNOWN"
    assert out.lifecycle_days_in_state == 1
    assert out.lifecycle_transition is False


def test_lifecycle_promotion_is_one_step_with_confirmation():
    cfg = deepcopy(DEFAULT_CONFIG)
    engine = LeaderLifecycleEngine(cfg)
    daily = _daily()
    base = _base_result(cfg, daily)

    discovery = replace(
        base,
        leader_score=65.0,
        market_leader_rank=30,
        leader_persistence_score=20.0,
        leader_persistence_level="LOW",
        turnover_top20_days_5d=0,
    )
    day1 = engine.enrich([discovery], {"111111": daily})[0]
    assert day1.lifecycle_state == "DISCOVERY"

    strong = replace(base, scan_date="20260826")
    day2 = engine.enrich([strong], {"111111": daily})[0]
    assert day2.lifecycle_state == "DISCOVERY"
    assert "emerging_confirmation_pending" in day2.lifecycle_reason

    day3 = engine.enrich(
        [replace(strong, scan_date="20260827")],
        {"111111": daily},
    )[0]
    assert day3.lifecycle_state == "EMERGING"

    day4 = engine.enrich(
        [replace(strong, scan_date="20260828")],
        {"111111": daily},
    )[0]
    assert day4.lifecycle_state == "EMERGING"

    day5 = engine.enrich(
        [replace(strong, scan_date="20260829")],
        {"111111": daily},
    )[0]
    assert day5.lifecycle_state == "LEADER"


def test_leader_score_collapse_alone_does_not_break_lifecycle():
    cfg = deepcopy(DEFAULT_CONFIG)
    engine = LeaderLifecycleEngine(cfg)
    daily = _daily()
    leader = _base_result(cfg, daily)

    day1 = engine.enrich([leader], {"111111": daily})[0]
    assert day1.lifecycle_state == "LEADER"

    weak = replace(
        leader,
        scan_date="20260826",
        leader_score=45.0,
        leader_persistence_score=55.0,
        leader_persistence_level="MEDIUM",
        chase_risk=10.0,
        breakout_exhaustion_risk=False,
        false_breakout_flag=False,
    )
    day2 = engine.enrich([weak], {"111111": daily})[0]
    assert day2.lifecycle_state == "LEADER"
    assert day2.lifecycle_broken_flags == 0
    assert "weakness_pending" in day2.lifecycle_reason

    day3 = engine.enrich(
        [replace(weak, scan_date="20260827")],
        {"111111": daily},
    )[0]
    assert day3.lifecycle_state == "EMERGING"
    assert day3.lifecycle_broken_flags == 0


def test_established_leader_structural_break_routes_through_exhausting():
    cfg = deepcopy(DEFAULT_CONFIG)
    engine = LeaderLifecycleEngine(cfg)
    healthy = _daily()
    leader = _base_result(cfg, healthy)

    day1 = engine.enrich([leader], {"111111": healthy})[0]
    assert day1.lifecycle_state == "LEADER"

    broken_daily = _daily(last_drop=True)
    broken = replace(
        leader,
        scan_date="20260826",
        price=float(broken_daily.iloc[-1]["close"]),
        leader_score=58.0,
    )
    day2 = engine.enrich([broken], {"111111": broken_daily})[0]
    assert day2.lifecycle_state == "EXHAUSTING"
    assert day2.lifecycle_broken_flags >= 1

    day3 = engine.enrich(
        [replace(broken, scan_date="20260827")],
        {"111111": broken_daily},
    )[0]
    assert day3.lifecycle_prev_state == "EXHAUSTING"
    assert day3.lifecycle_state == "BROKEN"


def test_multiple_degradation_signals_mark_exhausting_before_structure_breaks():
    cfg = deepcopy(DEFAULT_CONFIG)
    engine = LeaderLifecycleEngine(cfg)
    healthy = _daily()
    leader = _base_result(cfg, healthy)

    day1 = engine.enrich([leader], {"111111": healthy})[0]
    assert day1.lifecycle_state == "LEADER"

    exhausting = replace(
        leader,
        scan_date="20260826",
        leader_score=55.0,
        leader_persistence_score=30.0,
        leader_persistence_level="LOW",
    )
    day2 = engine.enrich([exhausting], {"111111": healthy})[0]
    assert day2.lifecycle_state == "EXHAUSTING"
    assert day2.lifecycle_exhaustion_flags >= 2
    assert day2.lifecycle_broken_flags == 0


def test_lifecycle_keeps_days_in_state_for_consecutive_leader_days():
    cfg = deepcopy(DEFAULT_CONFIG)
    engine = LeaderLifecycleEngine(cfg)
    daily = _daily()
    leader = _base_result(cfg, daily)

    day1 = engine.enrich([leader], {"111111": daily})[0]
    day2 = engine.enrich(
        [replace(leader, scan_date="20260826")],
        {"111111": daily},
    )[0]

    assert day1.lifecycle_state == "LEADER"
    assert day2.lifecycle_state == "LEADER"
    assert day2.lifecycle_days_in_state == 2
    assert day2.lifecycle_observed_days == 2
    assert day2.lifecycle_transition is False
