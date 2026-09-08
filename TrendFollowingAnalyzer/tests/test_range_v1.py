import pandas as pd

from trend_following_analyzer.backtest.range_v1 import parse_date_range, summarize_strategy_buckets


def test_parse_date_range_is_inclusive_and_validated():
    start, end = parse_date_range("20260102~20260130")
    assert start == pd.Timestamp("2026-01-02")
    assert end == pd.Timestamp("2026-01-30")


def test_strategy_summary_reports_signal_count_and_forward_stats():
    frame = pd.DataFrame(
        {
            "market": ["KOSPI", "KOSPI", "KOSDAQ"],
            "strategy_core": [True, True, False],
            "forward_D+5_return_pct": [10.0, -5.0, 20.0],
            "forward_D+20_return_pct": [20.0, 0.0, 30.0],
        }
    )
    summary = summarize_strategy_buckets(
        frame,
        horizons=(5, 20),
        strategy_flags=(("CORE", "strategy_core"),),
    )
    all_d5 = summary[(summary["market"] == "ALL") & (summary["strategy"] == "CORE") & (summary["horizon"] == "D+5")].iloc[0]
    assert int(all_d5["signal_count"]) == 2
    assert int(all_d5["complete_count"]) == 2
    assert abs(float(all_d5["avg_return_pct"]) - 2.5) < 1e-12
    assert abs(float(all_d5["median_return_pct"]) - 2.5) < 1e-12
    assert abs(float(all_d5["win_rate_pct"]) - 50.0) < 1e-12
