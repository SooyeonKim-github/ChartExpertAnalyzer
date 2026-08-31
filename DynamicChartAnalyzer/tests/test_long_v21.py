import numpy as np
import pandas as pd

from dynamic_chart_analyzer.long_v21 import score_long_events


def _events():
    return pd.DataFrame(
        {
            "signal_date": pd.to_datetime(["2026-08-28"] * 3),
            "ticker": ["A", "B", "C"],
            "source_rank": [3, 2, 1],
            "side": ["LONG", "LONG", "LONG"],
            "stage": [1, 2, 3],
            "rsi_rebound_strength": [8.0] * 3,
            "bullish_divergence_recent": [False] * 3,
            "macd_hist_slope": [0.1] * 3,
            "macd": [-1.0] * 3,
            "macd_hist_rising": [True] * 3,
            "tenkan_above_kijun": [True] * 3,
            "above_cloud": [True] * 3,
            "chikou_bullish": [True] * 3,
            "doji_risk": [False] * 3,
            "close_vs_ma60": [0.05] * 3,
            "close_vs_ma120": [0.08] * 3,
            "ma20_above_ma60": [True] * 3,
            "ma60_slope": [0.02] * 3,
            "rs_20": [0.02] * 3,
            "rs_60": [0.05] * 3,
            "rs_percentile_20": [0.8] * 3,
            "rs_percentile_60": [0.9] * 3,
            "volume_contraction_10d": [0.9] * 3,
            "volume_ratio_20": [1.0] * 3,
            "volume_ratio_5": [1.1] * 3,
            "breakout_volume_ratio": [1.3] * 3,
            "pullback_depth": [0.08] * 3,
            "distance_60d_high": [-0.1] * 3,
            "close_vs_atr": [0.5] * 3,
            "market_score": [4.0] * 3,
            "stop_distance_pct": [0.07] * 3,
            "chase_risk": ["LOW"] * 3,
        }
    )


def test_scores_are_separate_0_to_100_axes():
    out = score_long_events(_events())
    assert out["lecture_score"].between(0, 100).all()
    assert out["quality_score"].between(0, 100).all()
    assert out["combined_score"].between(0, 100).all()
    assert out["lecture_core_score_60"].between(0, 60).all()
    assert out["quality_enhancement_score_40"].between(0, 40).all()
    assert np.allclose(out["long_quality_score"], out["quality_score"])
    assert np.allclose(
        out["combined_score"],
        out["lecture_score"] * 0.60 + out["quality_score"] * 0.40,
    )


def test_quality_label_and_rank_do_not_require_later_stage():
    out = score_long_events(_events(), confirmed_score=70, watch_score=55)
    assert set(out["long_quality_label"]).issubset({"CONFIRMED", "WATCH", "REJECT"})
    assert sorted(out["daily_long_rank"].astype(int).tolist()) == [1, 2, 3]

    # Lecture confirmation should progress with Stage; quality is evaluated on a
    # separate axis and therefore is not required to rise with Stage.
    lecture = out.set_index("stage")["lecture_score"]
    assert lecture.loc[2] >= lecture.loc[1]
    assert lecture.loc[3] >= lecture.loc[2]
