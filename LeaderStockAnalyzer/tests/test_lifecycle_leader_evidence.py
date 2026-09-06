from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd

from leader_stock_analyzer.analyzer import LeaderStockAnalyzer
from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.lifecycle import LeaderLifecycleEngine


def _daily() -> pd.DataFrame:
    close = np.linspace(100.0, 120.0, 40)
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


def _base(cfg, daily):
    analyzer = LeaderStockAnalyzer(cfg)
    item = analyzer.analyze_one(
        scan_date="20260820",
        ticker="111111",
        name="EVIDENCE",
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
    return replace(
        item,
        persistence_available=True,
        leader_persistence_score=25.0,
        leader_persistence_level="LOW",
        turnover_top20_days_5d=1,
        chase_risk=10.0,
        breakout_exhaustion_risk=False,
        false_breakout_flag=False,
        emerging_available=True,
        strong_emerging_flag=False,
    )


def test_non_consecutive_leader_core_evidence_promotes_emerging_to_leader():
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["lifecycle"]["promotion_confirm_days"] = 2
    cfg["lifecycle"]["leader_evidence_required"] = 2
    cfg["lifecycle"]["leader_evidence_window_observations"] = 10

    daily = _daily()
    base = _base(cfg, daily)
    engine = LeaderLifecycleEngine(cfg)

    day1 = engine.enrich(
        [replace(base, leader_score=65.0, market_leader_rank=30, true_emerging_flag=False)],
        {"111111": daily},
    )[0]
    assert day1.lifecycle_state == "DISCOVERY"

    activation1 = replace(
        base,
        scan_date="20260821",
        leader_score=80.0,
        market_leader_rank=10,
        true_emerging_flag=True,
    )
    day2 = engine.enrich([activation1], {"111111": daily})[0]
    assert day2.lifecycle_state == "DISCOVERY"
    assert "pending_1/2" in day2.lifecycle_reason

    activation2 = replace(activation1, scan_date="20260824", leader_score=76.0)
    day3 = engine.enrich([activation2], {"111111": daily})[0]
    assert day3.lifecycle_state == "EMERGING"
    assert day3.lifecycle_reason == "confirmed_rank_velocity_emerging"

    cooldown = replace(
        activation2,
        scan_date="20260825",
        leader_score=65.0,
        market_leader_rank=30,
        true_emerging_flag=False,
    )
    day4 = engine.enrich([cooldown], {"111111": daily})[0]
    assert day4.lifecycle_state == "EMERGING"
    assert day4.lifecycle_reason == "leader_core_evidence_1/2"

    second_core = replace(
        cooldown,
        scan_date="20260826",
        leader_score=82.0,
        market_leader_rank=8,
        true_emerging_flag=False,
    )
    day5 = engine.enrich([second_core], {"111111": daily})[0]
    assert day5.lifecycle_state == "LEADER"
    assert day5.lifecycle_reason == "confirmed_emerging_to_leader_evidence_2/2"


def test_leader_evidence_respects_rolling_observation_window():
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["lifecycle"]["promotion_confirm_days"] = 2
    cfg["lifecycle"]["leader_evidence_required"] = 2
    cfg["lifecycle"]["leader_evidence_window_observations"] = 2

    daily = _daily()
    base = _base(cfg, daily)
    engine = LeaderLifecycleEngine(cfg)

    engine.enrich(
        [replace(base, leader_score=65.0, market_leader_rank=30, true_emerging_flag=False)],
        {"111111": daily},
    )
    first = replace(
        base,
        scan_date="20260821",
        leader_score=80.0,
        market_leader_rank=10,
        true_emerging_flag=True,
    )
    engine.enrich([first], {"111111": daily})
    entered = engine.enrich(
        [replace(first, scan_date="20260824")],
        {"111111": daily},
    )[0]
    assert entered.lifecycle_state == "EMERGING"

    hold = replace(
        first,
        leader_score=65.0,
        market_leader_rank=30,
        true_emerging_flag=False,
    )
    engine.enrich([replace(hold, scan_date="20260825")], {"111111": daily})
    day5 = engine.enrich([replace(hold, scan_date="20260826")], {"111111": daily})[0]
    assert day5.lifecycle_state == "EMERGING"
    assert day5.lifecycle_reason == "emerging_hold_conditions_held"

    new_core = replace(
        hold,
        scan_date="20260827",
        leader_score=82.0,
        market_leader_rank=8,
    )
    day6 = engine.enrich([new_core], {"111111": daily})[0]
    assert day6.lifecycle_state == "EMERGING"
    assert day6.lifecycle_reason == "leader_core_evidence_1/2"
