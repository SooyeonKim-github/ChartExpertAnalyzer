import numpy as np
import pandas as pd

from leader_stock_analyzer.analyzer import LeaderStockAnalyzer
from leader_stock_analyzer.config import DEFAULT_CONFIG


def _daily():
    n = 130
    close = np.linspace(100, 130, n)
    high = close + 2
    low = close - 2
    open_ = close - 1
    volume = np.full(n, 1_000_000.0)
    close[-1], high[-1], low[-1], open_[-1], volume[-1] = 150, 152, 145, 146, 2_000_000
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume, "trading_value": close * volume}, index=pd.date_range("2026-01-01", periods=n))


def test_missing_intraday_is_reweighted_not_zeroed():
    analyzer = LeaderStockAnalyzer(DEFAULT_CONFIG)
    r = analyzer.analyze_one(
        scan_date="20260902", ticker="123456", name="TEST", market="KOSDAQ",
        price=150, return_pct=12, trading_value=100_000_000_000, trading_value_rank=1,
        universe_size=100, daily=_daily(), intraday=pd.DataFrame(), market_return_pct=-1.0,
    )
    assert r.intraday_strength_score is None
    assert r.leader_score > 70


def test_finalize_assigns_rank_and_status():
    analyzer = LeaderStockAnalyzer(DEFAULT_CONFIG)
    a = analyzer.analyze_one(scan_date="20260902", ticker="111111", name="A", market="KOSDAQ", price=150, return_pct=15, trading_value=120_000_000_000, trading_value_rank=1, universe_size=100, daily=_daily(), intraday=pd.DataFrame(), market_return_pct=-1)
    b = analyzer.analyze_one(scan_date="20260902", ticker="222222", name="B", market="KOSDAQ", price=150, return_pct=5, trading_value=20_000_000_000, trading_value_rank=20, universe_size=100, daily=_daily(), intraday=pd.DataFrame(), market_return_pct=1)
    out = analyzer.finalize([b, a])
    assert out[0].ticker == "111111"
    assert out[0].market_leader_rank == 1
    assert out[0].status in {"STRONG_CONFIRMED", "CONFIRMED", "WATCH"}
