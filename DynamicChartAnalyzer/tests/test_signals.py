import numpy as np
import pandas as pd

from dynamic_chart_analyzer import StrategyConfig
from dynamic_chart_analyzer.indicators import add_indicators
from dynamic_chart_analyzer.signals import add_signals


def _sample_df(n=160):
    x = np.arange(n, dtype=float)
    close = 100 + np.sin(x / 8) * 8 + x * 0.04
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(n, 100_000.0),
        },
        index=pd.date_range("2025-01-01", periods=n, freq="D"),
    )


def test_signal_frame_has_enhanced_confirmation_columns():
    cfg = StrategyConfig()
    out = add_signals(add_indicators(_sample_df(), cfg), cfg)
    expected = {
        "bullish_divergence",
        "bearish_divergence",
        "macd_hist_rising",
        "cloud_width_atr",
        "thick_cloud",
        "bullish_engulfing",
        "cloud_retest_hold",
        "long_stage3",
    }
    assert expected.issubset(out.columns)
