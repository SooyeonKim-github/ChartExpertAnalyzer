from CloseBetAnalyzer.buy_day_guide import build_buy_day_guide
from CloseBetAnalyzer.config import CloseBetConfig


def test_buy_day_guide_orders_levels():
    guide = build_buy_day_guide(
        reference_close=100_000,
        ma5=98_000,
        nearest_support=96_000,
        cfg=CloseBetConfig(),
    )
    assert guide.cancel_below <= guide.hold_level
    assert guide.preferred_low < guide.reference_close < guide.preferred_high
    assert guide.preferred_high < guide.chase_above
