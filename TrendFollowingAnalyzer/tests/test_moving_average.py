import numpy as np
import pandas as pd

from trend_following_analyzer.indicators import add_moving_average_indicators


def test_ma50_ma150_and_slope_are_calculated_without_lookahead():
    close = np.arange(1.0, 221.0)
    df = pd.DataFrame({"close": close})

    out = add_moving_average_indicators(
        df,
        ma_short=50,
        ma_long=150,
        slope_lookback=20,
    )

    assert pd.isna(out.loc[48, "ma50"])
    assert out.loc[49, "ma50"] == np.mean(close[:50])
    assert pd.isna(out.loc[148, "ma150"])
    assert out.loc[149, "ma150"] == np.mean(close[:150])
    assert pd.isna(out.loc[168, "ma150_slope_pct"])
    assert out.loc[169, "ma150_slope_pct"] > 0
    assert out.iloc[-1]["close_vs_ma150_pct"] > 0


def test_invalid_ma_order_is_rejected():
    df = pd.DataFrame({"close": [1, 2, 3]})
    try:
        add_moving_average_indicators(df, ma_short=150, ma_long=50)
    except ValueError as exc:
        assert "ma_short" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
