import numpy as np
import pandas as pd

from trend_following_analyzer.regime import BEAR, BULL, NEUTRAL, classify_market_regime


def test_market_bull_uses_lecture_core_sign_not_experimental_threshold():
    close = np.linspace(100.0, 101.0, 260)
    df = pd.DataFrame({"close": close})
    snap = classify_market_regime(
        df,
        market="KOSPI",
        experimental_slope_threshold_pct=5.0,
    )
    assert snap.regime == BULL
    assert snap.market_eligible is True
    assert snap.lecture_ma150_position_pass is True
    assert snap.lecture_ma150_slope_pass is True
    assert snap.experimental_slope_threshold_pass is False


def test_market_bear():
    df = pd.DataFrame({"close": np.linspace(300.0, 100.0, 260)})
    snap = classify_market_regime(df, market="KOSDAQ")
    assert snap.regime == BEAR
    assert snap.market_eligible is False


def test_market_neutral_when_price_location_and_slope_disagree():
    rising = np.linspace(100.0, 300.0, 240)
    drop = np.linspace(300.0, 210.0, 20)
    df = pd.DataFrame({"close": np.concatenate([rising, drop])})
    snap = classify_market_regime(df, market="KOSPI")
    assert snap.regime in {NEUTRAL, BEAR}
    # Ensure no accidental BULL when latest price is below MA150 or slope is non-positive.
    assert snap.regime != BULL
