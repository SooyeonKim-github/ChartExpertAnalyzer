import numpy as np
import pandas as pd

from dynamic_chart_analyzer.long_v2 import (
    BASE_EVENT_FEATURE_COLUMNS,
    add_long_v2_features,
    add_rs_percentiles,
    prepare_market_features,
    score_long_events,
)


def _synthetic_analyzed():
    idx = pd.date_range("2023-01-02", periods=180, freq="B")
    close = pd.Series(
        np.linspace(100.0, 140.0, len(idx)) + np.sin(np.arange(len(idx)) / 5.0) * 3.0,
        index=idx,
    )
    out = pd.DataFrame(index=idx)
    out["open"] = close * 0.995
    out["high"] = close * 1.01
    out["low"] = close * 0.99
    out["close"] = close
    out["volume"] = 1_000_000 * (1.0 + 0.10 * np.sin(np.arange(len(idx))))
    out["rsi"] = 50.0 + 10.0 * np.sin(np.arange(len(idx)) / 7.0)
    out["atr"] = 2.0
    out["macd"] = np.sin(np.arange(len(idx)) / 10.0)
    out["macd_signal"] = np.sin(np.arange(len(idx)) / 10.0 - 0.2)
    out["macd_hist"] = out["macd"] - out["macd_signal"]
    out["tenkan"] = close.rolling(9).mean()
    out["kijun"] = close.rolling(26).mean()
    out["cloud_top"] = close.rolling(52).mean()
    out["cloud_bottom"] = out["cloud_top"] * 0.98
    out["cloud_width"] = out["cloud_top"] - out["cloud_bottom"]
    out["chikou_reference_price"] = close.shift(26)
    out["cloud_retest_hold"] = False
    out["long_stop_reference"] = out["low"].rolling(5).min().shift(1)
    return out


def test_long_v2_adds_requested_features():
    analyzed = _synthetic_analyzed()
    market = prepare_market_features(
        pd.DataFrame(
            {"close": np.linspace(100.0, 120.0, len(analyzed))},
            index=analyzed.index,
        )
    )
    out = add_long_v2_features(analyzed, market)
    missing = [col for col in BASE_EVENT_FEATURE_COLUMNS if col not in out.columns]
    assert missing == []
    assert out["market_regime"].iloc[-1] in {"BULL", "NEUTRAL", "BEAR"}
    assert out["chase_risk"].iloc[-1] in {"LOW", "MEDIUM", "HIGH"}


def test_rs_percentiles_use_full_cross_section():
    dt = pd.Timestamp("2026-08-28")
    panel = pd.DataFrame(
        {
            "signal_date": [dt, dt, dt],
            "ticker": ["A", "B", "C"],
            "rs_20": [-0.1, 0.0, 0.2],
            "rs_60": [0.3, 0.1, -0.2],
        }
    )
    out = add_rs_percentiles(panel)
    assert out.loc[out["ticker"].eq("C"), "rs_percentile_20"].iloc[0] == 1.0
    assert out.loc[out["ticker"].eq("A"), "rs_percentile_60"].iloc[0] == 1.0


def test_long_quality_score_is_lecture_first_and_ranked():
    analyzed = _synthetic_analyzed()
    market = prepare_market_features(
        pd.DataFrame(
            {"close": np.linspace(100.0, 120.0, len(analyzed))},
            index=analyzed.index,
        )
    )
    enriched = add_long_v2_features(analyzed, market)
    row = enriched.iloc[-1]

    events = pd.DataFrame(
        {
            "signal_date": [enriched.index[-1]] * 3,
            "ticker": ["A", "B", "C"],
            "source_rank": [3, 2, 1],
            "side": ["LONG", "LONG", "LONG"],
            "stage": [1, 2, 3],
        }
    )
    for col in BASE_EVENT_FEATURE_COLUMNS:
        events[col] = [row[col], row[col], row[col]]
    events["rs_percentile_20"] = [0.9, 0.9, 0.9]
    events["rs_percentile_60"] = [0.9, 0.9, 0.9]

    out = score_long_events(events)
    assert out["long_quality_score"].between(0, 100).all()
    assert out["lecture_score"].between(0, 60).all()
    assert out["lecture_rsi_score"].between(0, 15).all()
    assert out["lecture_macd_score"].between(0, 20).all()
    assert out["lecture_ichimoku_score"].between(0, 25).all()
    assert out["quality_enhancement_score"].between(0, 40).all()
    assert np.allclose(
        out["long_quality_score"],
        out["lecture_score"] + out["quality_enhancement_score"],
    )
    assert set(out["long_quality_label"]).issubset({"CONFIRMED", "WATCH", "REJECT"})
    assert sorted(out["daily_long_rank"].astype(int).tolist()) == [1, 2, 3]

    # With otherwise identical features, chronological lecture confirmation should
    # never make a later stage score lower than Stage1.
    scores = out.set_index("stage")["lecture_score"]
    assert scores.loc[2] >= scores.loc[1]
    assert scores.loc[3] >= scores.loc[2]
