from copy import deepcopy

import numpy as np
import pandas as pd

from leader_stock_analyzer.analyzer import LeaderStockAnalyzer
from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.persistence import PersistenceEngine
from leader_stock_analyzer.sector_context import SectorContextEngine


def _daily(start: float, end: float, trading_value: float, n: int = 40) -> pd.DataFrame:
    close = np.linspace(start, end, n)
    volume = np.full(n, 1_000_000.0)
    tv = np.full(n, trading_value)
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
            "trading_value": tv,
        },
        index=pd.date_range("2026-07-01", periods=n, freq="B"),
    )


def _result(analyzer, ticker: str, name: str, market: str, daily: pd.DataFrame, rank: int, ret: float):
    return analyzer.analyze_one(
        scan_date="20260825",
        ticker=ticker,
        name=name,
        market=market,
        price=float(daily.iloc[-1]["close"]),
        return_pct=ret,
        trading_value=float(daily.iloc[-1]["trading_value"]),
        trading_value_rank=rank,
        universe_size=4,
        daily=daily,
        intraday=pd.DataFrame(),
        market_return_pct=0.0,
    )


def test_sector_context_ranks_strong_sector_and_sector_leader():
    cfg = deepcopy(DEFAULT_CONFIG)
    analyzer = LeaderStockAnalyzer(cfg)
    daily = {
        "111111": _daily(100, 140, 120_000_000_000),
        "222222": _daily(100, 125, 80_000_000_000),
        "333333": _daily(100, 101, 50_000_000_000),
        "444444": _daily(100, 98, 40_000_000_000),
    }
    results = [
        _result(analyzer, "111111", "A", "KOSPI", daily["111111"], 1, 8.0),
        _result(analyzer, "222222", "B", "KOSPI", daily["222222"], 2, 4.0),
        _result(analyzer, "333333", "C", "KOSPI", daily["333333"], 3, 0.5),
        _result(analyzer, "444444", "D", "KOSPI", daily["444444"], 4, -1.0),
    ]
    sector_map = {"111111": "TECH", "222222": "TECH", "333333": "FIN", "444444": "FIN"}
    out = SectorContextEngine(cfg).enrich(
        results,
        daily_by_ticker=daily,
        sector_map=sector_map,
        market_period_returns={"KOSPI": {5: 0.0, 20: 0.0}},
    )
    by_ticker = {x.ticker: x for x in out}
    assert by_ticker["111111"].sector == "TECH"
    assert by_ticker["111111"].sector_context_reliable is True
    assert by_ticker["111111"].sector_market_rank < by_ticker["333333"].sector_market_rank
    assert by_ticker["111111"].sector_leader_rank == 1


def test_persistence_detects_consistent_trading_value_leader():
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["persistence"]["top_rank"] = 1
    cfg["persistence"]["broad_rank"] = 2
    cfg["persistence"]["strong_return_pct"] = 0.0
    analyzer = LeaderStockAnalyzer(cfg)

    leader = _daily(100, 130, 150_000_000_000)
    follower = _daily(100, 110, 60_000_000_000)
    others = _daily(100, 105, 30_000_000_000)
    weak = _daily(100, 100, 10_000_000_000)
    daily = {"111111": leader, "222222": follower, "333333": others, "444444": weak}
    results = [
        _result(analyzer, "111111", "A", "KOSPI", leader, 1, 5.0),
        _result(analyzer, "222222", "B", "KOSPI", follower, 2, 2.0),
        _result(analyzer, "333333", "C", "KOSPI", others, 3, 1.0),
        _result(analyzer, "444444", "D", "KOSPI", weak, 4, 0.0),
    ]
    out = PersistenceEngine(cfg).enrich(results, daily_by_ticker=daily)
    by_ticker = {x.ticker: x for x in out}
    assert by_ticker["111111"].persistence_available is True
    assert by_ticker["111111"].turnover_top20_days_5d == 5
    assert by_ticker["111111"].turnover_rank_avg_5d == 1.0
    assert by_ticker["111111"].leader_persistence_level == "HIGH"
