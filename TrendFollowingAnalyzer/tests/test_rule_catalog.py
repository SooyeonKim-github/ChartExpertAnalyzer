from trend_following_analyzer.rule_catalog import (
    ACTIVE_FILTER,
    BACKTEST_ONLY,
    EXPERIMENTAL,
    LECTURE_CORE,
    RULE_CATALOG,
)


def test_experimental_rules_do_not_default_to_active_filter():
    experimental = [r for r in RULE_CATALOG if r.origin == EXPERIMENTAL]
    assert experimental
    assert all(r.mode != ACTIVE_FILTER for r in experimental)


def test_lecture_core_has_active_market_and_trend_rules():
    active_core = {
        r.key for r in RULE_CATALOG
        if r.origin == LECTURE_CORE and r.mode == ACTIVE_FILTER
    }
    assert "trend.ma150_position" in active_core
    assert "trend.ma150_slope" in active_core
    assert "market.ma150_position" in active_core
    assert "market.ma150_slope" in active_core


def test_52w_breadth_is_lecture_core_but_backtest_only():
    rule = next(r for r in RULE_CATALOG if r.key == "market.52w_high_breadth")
    assert rule.origin == LECTURE_CORE
    assert rule.mode == BACKTEST_ONLY
