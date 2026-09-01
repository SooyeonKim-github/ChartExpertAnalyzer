import pandas as pd
import pytest

import main_range
from main_range import _add_forward_metrics, _latest_market_date, parse_date_range


def test_latest_market_date_uses_per_ticker_calendar(monkeypatch):
    cal = pd.DataFrame(
        {"close": [70000, 70500]},
        index=pd.to_datetime(["2026-08-27", "2026-08-28"]),
    )

    def fake_load_pykrx(ticker, start, end):
        assert ticker == "005930"
        return cal

    monkeypatch.setattr(main_range, "load_pykrx", fake_load_pykrx)
    assert _latest_market_date(None, pd.Timestamp("2026-08-31")) == "20260828"


def test_parse_date_range():
    start, end = parse_date_range("20260101~20260831")
    assert start == pd.Timestamp("2026-01-01")
    assert end == pd.Timestamp("2026-08-31")


def test_forward_metrics_start_from_next_trading_bar():
    idx = pd.to_datetime(["2026-08-27", "2026-08-28", "2026-08-31"])
    prices = pd.DataFrame(
        {
            "close": [100.0, 110.0, 120.0],
            "high": [101.0, 112.0, 123.0],
            "low": [99.0, 108.0, 118.0],
        },
        index=idx,
    )
    event = {
        "signal_date": pd.Timestamp("2026-08-27"),
        "entry_price": 100.0,
        "direction": 1,
    }
    out = _add_forward_metrics(event, prices, forward_bars=2)
    assert out["D+1"] == pytest.approx(0.10)
    assert out["D+2"] == pytest.approx(0.20)
    assert out["forward_complete"] is True
