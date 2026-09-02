import numpy as np
import pandas as pd

from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.signals.daily_position import score_daily_position
from leader_stock_analyzer.signals.intraday_strength import score_intraday_strength
from leader_stock_analyzer.signals.price_strength import score_price_strength
from leader_stock_analyzer.signals.timing import score_timing


def _daily(breakout=True):
    n = 130
    close = np.linspace(100, 130, n)
    high = close + 2
    low = close - 2
    open_ = close - 1
    volume = np.full(n, 1_000_000.0)
    if breakout:
        close[-1] = 150
        high[-1] = 152
        low[-1] = 145
        open_[-1] = 146
        volume[-1] = 2_000_000
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume, "trading_value": close * volume}, index=pd.date_range("2026-01-01", periods=n))


def test_price_strength_thresholds():
    assert score_price_strength(10).score == 90
    assert score_price_strength(5).score == 65
    assert score_price_strength(-1).score == 0


def test_daily_position_detects_breakout():
    sig = score_daily_position(_daily(True))
    assert sig.details["high_20d_break"] is True
    assert sig.details["close_20d_high"] is True


def test_intraday_strength_available():
    close = pd.Series([100, 101, 102, 103, 104, 108, 109, 110, 111, 112], dtype=float)
    intraday = pd.DataFrame({
        "open": close - 0.5,
        "high": close + 0.5,
        "low": close - 1,
        "close": close,
        "volume": [5_000_000] * len(close),
        "trading_value": [600_000_000] * len(close),
    })
    sig = score_intraday_strength(intraday, DEFAULT_CONFIG)
    assert sig.score is not None
    assert sig.details["high_break_count"] > 0


def test_daily_timing_does_not_fake_pullback():
    d = _daily(True)
    pos = score_daily_position(d)
    t = score_timing(d, pd.DataFrame(), pos.details["breakout_reference"])
    assert t.source == "daily_proxy"
    assert t.entry_state == "DAILY_BREAKOUT_PROXY"
