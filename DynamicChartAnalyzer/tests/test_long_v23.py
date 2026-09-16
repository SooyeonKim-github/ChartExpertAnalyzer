import numpy as np
import pandas as pd

from dynamic_chart_analyzer.long_v23 import score_long_events


def _base_events(tickers=None, stages=None, dates=None):
    tickers = tickers or ["A", "B", "C"]
    stages = stages or [1, 2, 3]
    dates = dates or ["2026-08-01", "2026-08-05", "2026-08-12"]
    n = len(stages)
    return pd.DataFrame(
        {
            "signal_date": pd.to_datetime(dates),
            "ticker": tickers,
            "source_rank": list(range(1, n + 1)),
            "side": ["LONG"] * n,
            "stage": stages,
            "rsi": [45.0] * n,
            "rsi_rebound_strength": [8.0] * n,
            "bullish_divergence_recent": [True] * n,
            "macd_hist_slope": [0.1] * n,
            "macd": [-0.5] * n,
            "macd_hist_rising": [True] * n,
            "tenkan_above_kijun": [True] * n,
            "above_cloud": [True] * n,
            "chikou_bullish": [True] * n,
            "doji_risk": [False] * n,
            "close_vs_ma60": [0.05] * n,
            "ma20_slope": [0.01] * n,
            "ma20_above_ma60": [True] * n,
            "ma60_slope": [0.02] * n,
            "rs_20": [0.02] * n,
            "rs_60": [0.05] * n,
            "rs_percentile_20": [0.65] * n,
            "rs_percentile_60": [0.80] * n,
            "volume_contraction_10d": [0.85] * n,
            "volume_ratio_20": [1.0] * n,
            "volume_ratio_5": [1.1] * n,
            "breakout_volume_ratio": [1.2] * n,
            "pullback_depth": [0.15] * n,
            "distance_60d_high": [-0.10] * n,
            "distance_20d_high": [-0.08] * n,
            "close_vs_atr": [0.5] * n,
            "market_score": [1.0] * n,
            "stop_distance_pct": [0.07] * n,
            "atr_pct": [0.03] * n,
            "chase_risk": ["LOW"] * n,
            "cloud_distance": [0.02] * n,
            "cloud_thickness": [0.03] * n,
            "tenkan_kijun_gap": [0.01] * n,
            "cloud_retest": [True] * n,
        }
    )


def test_v23_uses_stage_specific_components():
    out = score_long_events(_base_events())
    assert out["quality_version"].tolist() == ["V2.3", "V2.3", "V2.3"]
    assert out.loc[out["stage"].eq(1), "stage_reversal_score"].iloc[0] > 0
    assert out.loc[out["stage"].eq(1), "stage_momentum_score"].iloc[0] == 0
    assert out.loc[out["stage"].eq(2), "stage_momentum_score"].iloc[0] > 0
    assert out.loc[out["stage"].eq(3), "stage_breakout_score"].iloc[0] > 0
    assert out.loc[out["stage"].eq(3), "stage_extension_score"].iloc[0] > 0
    assert out["stage_quality_score"].between(0, 100).all()
    assert np.allclose(out["quality_score"], out["stage_quality_score"])


def test_market_and_risk_are_separate_from_alpha_quality():
    events = _base_events(tickers=["A", "B"], stages=[1, 1], dates=["2026-08-01", "2026-08-01"])
    events.loc[0, ["market_score", "stop_distance_pct", "atr_pct", "chase_risk"]] = [1.0, 0.05, 0.03, "LOW"]
    events.loc[1, ["market_score", "stop_distance_pct", "atr_pct", "chase_risk"]] = [5.0, 0.20, 0.09, "HIGH"]
    out = score_long_events(events)

    assert out["stage_quality_score"].nunique() == 1
    assert out["quality_market_score"].tolist() == [0.0, 0.0]
    assert out["quality_risk_score"].tolist() == [0.0, 0.0]
    assert out["market_context"].tolist() == ["REVERSAL_ENV", "TREND_ENV"]
    assert out["risk_level"].tolist() == ["LOW", "HIGH"]


def test_setup_id_and_stage3_deployable_are_research_only_outputs():
    events = _base_events(
        tickers=["005930", "005930", "005930", "005930"],
        stages=[1, 2, 3, 1],
        dates=["2026-08-01", "2026-08-05", "2026-08-12", "2026-09-01"],
    )
    out = score_long_events(events)

    assert out["setup_id"].iloc[0] == out["setup_id"].iloc[1] == out["setup_id"].iloc[2]
    assert out["setup_id"].iloc[3] != out["setup_id"].iloc[0]
    stage3 = out[out["stage"].eq(3)].iloc[0]
    assert stage3["stage3_trigger_type"] == "CLOUD_RETEST"
    assert bool(stage3["stage3_deployable"])
    assert stage3["stage3_deploy_reason"] == "QUALITY_CONFIRMED_RESEARCH_ONLY"

    stricter = score_long_events(events.iloc[:3], stage_thresholds={3: (101.0, 90.0)})
    stage3_strict = stricter[stricter["stage"].eq(3)].iloc[0]
    assert not bool(stage3_strict["stage3_deployable"])
