import pandas as pd

from trend_following_analyzer.regime.intraday_strength import INTRADAY_IMPROVING, INTRADAY_INSUFFICIENT, STRONG_OPEN_WEAK_CLOSE, WEAK_OPEN_STRONG_CLOSE, compute_intraday_strength_history


def _df(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.date_range("2026-01-01", periods=len(rows), freq="D"))


def test_gap_down_strong_close_is_weak_open_strong_close():
    out = compute_intraday_strength_history(_df([[100,101,99,100],[98,104,96,103]]))
    assert out.iloc[-1]["intraday_label"] == WEAK_OPEN_STRONG_CLOSE
    assert out.iloc[-1]["close_location_value"] >= 0.70


def test_gap_up_weak_close_is_strong_open_weak_close():
    out = compute_intraday_strength_history(_df([[100,101,99,100],[103,105,97,98]]))
    assert out.iloc[-1]["intraday_label"] == STRONG_OPEN_WEAK_CLOSE
    assert out.iloc[-1]["close_location_value"] <= 0.30


def test_zero_range_does_not_divide_by_zero():
    out = compute_intraday_strength_history(_df([[100,101,99,100],[100,100,100,100]]))
    assert pd.isna(out.iloc[-1]["close_location_value"])
    assert out.iloc[-1]["intraday_label"] == INTRADAY_INSUFFICIENT


def test_rolling_direction_detects_improvement():
    rows = [[100,101,95,96]] * 15 + [[100,102,98,100]] * 5 + [[100,105,99,104]] * 5
    out = compute_intraday_strength_history(_df(rows), short_window=5, long_window=20)
    assert out.iloc[-1]["strong_close_5d_ratio"] == 100.0
    assert out.iloc[-1]["weak_close_5d_ratio"] == 0.0
    assert out.iloc[-1]["intraday_direction"] == INTRADAY_IMPROVING


def test_future_rows_do_not_change_past_intraday_metrics():
    base = _df([[100,103,97,102]] * 25)
    full = compute_intraday_strength_history(base)
    cutoff = base.index[19]
    prefix = compute_intraday_strength_history(base.loc[:cutoff])
    for col in ["close_location_value","strong_close_5d_ratio","strong_close_20d_ratio","weak_close_5d_ratio","weak_close_20d_ratio"]:
        assert full.loc[cutoff, col] == prefix.loc[cutoff, col]
