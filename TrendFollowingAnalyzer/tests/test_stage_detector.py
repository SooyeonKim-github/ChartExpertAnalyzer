import numpy as np
import pandas as pd

from trend_following_analyzer.indicators import add_moving_average_indicators
from trend_following_analyzer.regime import STAGE_1, STAGE_2, STAGE_3, STAGE_4, add_stage_labels


def _classify(close_values, threshold=0.30):
    df = pd.DataFrame({"close": np.asarray(close_values, dtype=float)})
    out = add_moving_average_indicators(df, ma_short=50, ma_long=150, slope_lookback=20)
    return add_stage_labels(out, slope_threshold_pct=threshold)


def test_strong_uptrend_is_stage2():
    out = _classify(np.linspace(100, 300, 260))
    assert out.iloc[-1]["stage"] == STAGE_2
    assert bool(out.iloc[-1]["trend_eligible"]) is True


def test_strong_downtrend_is_stage4():
    out = _classify(np.linspace(300, 100, 260))
    assert out.iloc[-1]["stage"] == STAGE_4


def test_experimental_threshold_does_not_gate_stage2():
    out = _classify(np.linspace(100.0, 101.0, 260), threshold=5.0)
    assert out.iloc[-1]["stage"] == STAGE_2
    assert bool(out.iloc[-1]["stage_experimental_slope_pass"]) is False


def test_transition_after_stage4_becomes_stage1():
    falling = np.linspace(300, 130, 220)
    flat = np.full(180, 130.0)
    out = _classify(np.concatenate([falling, flat]))
    assert STAGE_4 in set(out["stage"])
    assert out.iloc[-1]["stage"] == STAGE_1


def test_transition_after_stage2_becomes_stage3():
    rising = np.linspace(100, 280, 220)
    flat = np.full(180, 280.0)
    out = _classify(np.concatenate([rising, flat]))
    assert STAGE_2 in set(out["stage"])
    assert out.iloc[-1]["stage"] == STAGE_3
