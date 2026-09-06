import pandas as pd

from trend_following_analyzer.regime.breadth import (
    AVAILABLE,
    IMPROVING,
    LOW_COVERAGE,
    compute_52w_breadth_history,
    latest_breadth_snapshot,
)


def _rows(values_by_ticker):
    dates = pd.date_range("2025-01-01", periods=max(map(len, values_by_ticker.values())), freq="B")
    rows = []
    for ticker, values in values_by_ticker.items():
        for date, close in zip(dates, values):
            rows.append({"date": date, "ticker": ticker, "close": close})
    return pd.DataFrame(rows)


def test_full_history_tickers_enter_denominator_only_after_min_history():
    df = _rows({"A": [1, 2, 3, 4, 5, 6], "B": [6, 5, 4, 3, 2, 1]})
    hist = compute_52w_breadth_history(
        df, lookback_sessions=5, min_history_sessions=5, short_window=2, long_window=3
    )
    assert int(hist.iloc[3]["eligible_count"]) == 0
    assert int(hist.iloc[4]["eligible_count"]) == 2
    assert int(hist.iloc[4]["new_high_52w_count"]) == 1
    assert int(hist.iloc[4]["new_low_52w_count"]) == 1
    assert float(hist.iloc[4]["new_high_52w_ratio"]) == 50.0


def test_short_listing_is_excluded_from_eligible_denominator():
    df = _rows({"A": [1, 2, 3, 4, 5, 6], "IPO": [10, 11, 12]})
    hist = compute_52w_breadth_history(
        df, lookback_sessions=5, min_history_sessions=5, short_window=2, long_window=3
    )
    last = hist.iloc[-1]
    assert int(last["universe_count"]) == 1
    assert int(last["eligible_count"]) == 1


def test_latest_snapshot_marks_low_coverage_without_using_it_as_filter():
    df = _rows({"A": [1, 2, 3, 4, 5], "B": [1, 2], "C": [1, 2]})
    hist = compute_52w_breadth_history(
        df, lookback_sessions=3, min_history_sessions=3, short_window=1, long_window=2
    )
    snap = latest_breadth_snapshot(
        hist, market="KOSPI", min_coverage_ratio=0.8, snapshot_dates_loaded=5, snapshot_dates_expected=5
    )
    assert snap.status in {AVAILABLE, LOW_COVERAGE}
    assert snap.measurement == "52W_CLOSE_HIGH_PROXY"
    assert snap.snapshot_date_coverage_ratio == 1.0


def test_breadth_change_is_point_in_time_and_can_improve():
    df = _rows({"A": [1, 2, 3, 4, 5, 6, 7], "B": [2, 2, 2, 2, 2, 2, 2]})
    hist = compute_52w_breadth_history(
        df, lookback_sessions=3, min_history_sessions=3, short_window=2, long_window=3
    )
    assert pd.isna(hist.iloc[1]["new_high_52w_ratio"])
    assert float(hist.iloc[-1]["new_high_52w_ratio"]) >= 50.0
    assert hist.iloc[-1]["breadth_direction"] in {IMPROVING, "MIXED"}
