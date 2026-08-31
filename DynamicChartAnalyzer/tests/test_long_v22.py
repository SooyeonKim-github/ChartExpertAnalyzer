import numpy as np
import pandas as pd

from dynamic_chart_analyzer.long_v22 import score_long_events


def _events():
    return pd.DataFrame(
        {
            "signal_date": pd.to_datetime(["2026-08-28"] * 3),
            "ticker": ["A", "B", "C"],
            "source_rank": [3, 2, 1],
            "side": ["LONG", "LONG", "LONG"],
            "stage": [1, 2, 3],
            # lecture axis inputs
            "rsi_rebound_strength": [8.0] * 3,
            "bullish_divergence_recent": [False] * 3,
            "macd_hist_slope": [0.1] * 3,
            "macd": [-1.0] * 3,
            "macd_hist_rising": [True] * 3,
            "tenkan_above_kijun": [True] * 3,
            "above_cloud": [True] * 3,
            "chikou_bullish": [True] * 3,
            "doji_risk": [False] * 3,
            # V2.2 quality inputs: identical on purpose across stages
            "close_vs_ma60": [0.05] * 3,
            "close_vs_ma120": [0.08] * 3,
            "ma20_slope": [0.01] * 3,
            "ma20_above_ma60": [True] * 3,
            "ma60_slope": [0.02] * 3,
            "rs_20": [0.02] * 3,
            "rs_60": [0.05] * 3,
            "rs_percentile_20": [0.65] * 3,
            "rs_percentile_60": [0.80] * 3,
            "volume_contraction_10d": [0.85] * 3,
            "volume_ratio_20": [1.0] * 3,
            "volume_ratio_5": [1.0] * 3,
            "breakout_volume_ratio": [1.0] * 3,
            "pullback_depth": [0.15] * 3,
            "distance_60d_high": [-0.10] * 3,
            "close_vs_atr": [0.5] * 3,
            "market_score": [1.0, 3.0, 5.0],
            "stop_distance_pct": [0.09] * 3,
            "chase_risk": ["LOW"] * 3,
        }
    )


def test_v22_quality_is_stage_independent_when_quality_features_match():
    out = score_long_events(_events())
    assert out["quality_score"].between(0, 100).all()
    # Different stages must not structurally inflate secondary quality.
    assert out["quality_score"].nunique() == 1
    # Lecture confirmation remains a separate chronological axis.
    lecture = out.set_index("stage")["lecture_score"]
    assert lecture.loc[2] >= lecture.loc[1]
    assert lecture.loc[3] >= lecture.loc[2]


def test_market_context_is_tagged_but_not_directionally_ranked():
    out = score_long_events(_events())
    assert out["market_context"].tolist() == [
        "REVERSAL_ENV",
        "NEUTRAL_ENV",
        "TREND_ENV",
    ]
    # All known contexts receive identical neutral market credit.
    assert out["quality_market_score"].tolist() == [10.0, 10.0, 10.0]
    assert out["quality_score"].nunique() == 1


def test_component_weights_and_labels_are_valid():
    out = score_long_events(_events(), confirmed_score=70, watch_score=55)
    caps = {
        "quality_rs_score": 25,
        "quality_trend_score": 20,
        "quality_price_structure_score": 15,
        "quality_volume_score": 15,
        "quality_market_score": 10,
        "quality_risk_score": 15,
    }
    for col, cap in caps.items():
        assert out[col].between(0, cap).all()

    component_sum = sum(out[col] for col in caps)
    assert np.allclose(out["quality_score"], component_sum)
    assert np.allclose(out["long_quality_score"], out["quality_score"])
    assert set(out["long_quality_label"]).issubset({"CONFIRMED", "WATCH", "REJECT"})
    assert sorted(out["daily_long_rank"].astype(int).tolist()) == [1, 2, 3]
