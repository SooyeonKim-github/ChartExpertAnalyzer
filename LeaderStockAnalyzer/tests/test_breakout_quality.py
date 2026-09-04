import numpy as np
import pandas as pd

from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.signals.breakout_quality import score_breakout_quality
from leader_stock_analyzer.signals.daily_position import score_daily_position


def _base_daily():
    n = 130
    close = np.linspace(100.0, 130.0, n)
    high = close + 2.0
    low = close - 2.0
    open_ = close - 0.5
    volume = np.full(n, 1_000_000.0)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "trading_value": close * volume,
        },
        index=pd.date_range("2026-01-01", periods=n),
    )


def test_primary_breakout_prefers_previous_high():
    d = _base_daily()
    d.iloc[-1, d.columns.get_loc("open")] = 132.0
    d.iloc[-1, d.columns.get_loc("high")] = 135.0
    d.iloc[-1, d.columns.get_loc("low")] = 131.8
    d.iloc[-1, d.columns.get_loc("close")] = 134.8
    d.iloc[-1, d.columns.get_loc("volume")] = 3_000_000.0
    d.iloc[-1, d.columns.get_loc("trading_value")] = 134.8 * 3_000_000.0
    pos = score_daily_position(d)
    assert pos.details["breakout_type"] == "PREVIOUS_HIGH_BREAK"
    assert pos.details["breakout_reference"] is not None


def test_clean_or_valid_breakout_scores_high():
    d = _base_daily()
    d.iloc[-1, d.columns.get_loc("open")] = 132.0
    d.iloc[-1, d.columns.get_loc("high")] = 135.0
    d.iloc[-1, d.columns.get_loc("low")] = 131.8
    d.iloc[-1, d.columns.get_loc("close")] = 134.8
    d.iloc[-1, d.columns.get_loc("volume")] = 3_000_000.0
    d.iloc[-1, d.columns.get_loc("trading_value")] = 134.8 * 3_000_000.0
    pos = score_daily_position(d)
    q = score_breakout_quality(d, pos.details["breakout_reference"], pos.details["breakout_type"], DEFAULT_CONFIG)
    assert q.available is True
    assert q.score is not None and q.score >= 70
    assert q.label in {"CLEAN_BREAKOUT", "VALID_BREAKOUT"}
    assert q.false_breakout is False


def test_failed_breakout_when_close_falls_back_below_level():
    d = _base_daily()
    d.iloc[-1, d.columns.get_loc("open")] = 130.0
    d.iloc[-1, d.columns.get_loc("high")] = 134.0
    d.iloc[-1, d.columns.get_loc("low")] = 126.0
    d.iloc[-1, d.columns.get_loc("close")] = 128.0
    d.iloc[-1, d.columns.get_loc("volume")] = 3_000_000.0
    d.iloc[-1, d.columns.get_loc("trading_value")] = 128.0 * 3_000_000.0
    pos = score_daily_position(d)
    assert pos.details["breakout_type"] is not None
    q = score_breakout_quality(d, pos.details["breakout_reference"], pos.details["breakout_type"], DEFAULT_CONFIG)
    assert q.false_breakout is True
    assert q.label == "FAILED_BREAKOUT"


def test_no_breakout_has_no_quality_score():
    d = _base_daily()
    prev = d.iloc[-2]
    d.iloc[-1, d.columns.get_loc("open")] = float(prev["open"])
    d.iloc[-1, d.columns.get_loc("high")] = float(prev["high"])
    d.iloc[-1, d.columns.get_loc("low")] = float(prev["low"])
    d.iloc[-1, d.columns.get_loc("close")] = float(prev["close"])
    d.iloc[-1, d.columns.get_loc("volume")] = float(prev["volume"])
    d.iloc[-1, d.columns.get_loc("trading_value")] = float(prev["trading_value"])
    pos = score_daily_position(d)
    assert pos.details["breakout_type"] is None
    q = score_breakout_quality(d, pos.details["breakout_reference"], pos.details["breakout_type"], DEFAULT_CONFIG)
    assert q.available is False
    assert q.score is None
    assert q.label == "NO_BREAKOUT"
