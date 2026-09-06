from trend_following_analyzer.rule_catalog import (
    ACTIVE_FILTER,
    BACKTEST_ONLY,
    EXPERIMENTAL,
    LECTURE_CORE,
    RULE_CATALOG,
)


def test_experimental_rules_do_not_default_to_active_filter():
    rules = [rule for rule in RULE_CATALOG if rule.origin == EXPERIMENTAL]
    assert rules and all(rule.mode != ACTIVE_FILTER for rule in rules)


def test_lecture_core_has_active_market_and_trend_rules():
    active = {
        rule.key
        for rule in RULE_CATALOG
        if rule.origin == LECTURE_CORE and rule.mode == ACTIVE_FILTER
    }
    assert {
        "trend.ma150_position",
        "trend.ma150_slope",
        "market.ma150_position",
        "market.ma150_slope",
    }.issubset(active)


def test_backtest_only_lecture_concepts_remain_non_gating():
    keys = {
        "market.52w_high_breadth",
        "market.intraday_strength",
        "stock.relative_strength",
        "stock.prior_advance",
        "stock.base_structure",
    }
    rules = [rule for rule in RULE_CATALOG if rule.key in keys]
    assert {rule.key for rule in rules} == keys
    assert all(rule.origin == LECTURE_CORE and rule.mode == BACKTEST_ONLY for rule in rules)


def test_base_numeric_rules_are_experimental_backtest_only():
    keys = {
        "stock.base_window",
        "stock.base_depth",
        "stock.base_price_contraction",
        "stock.base_resistance_tolerance",
        "stock.prior_advance_freshness",
        "stock.prior_advance_retention",
    }
    rules = [rule for rule in RULE_CATALOG if rule.key in keys]
    assert {rule.key for rule in rules} == keys
    assert all(rule.origin == EXPERIMENTAL and rule.mode == BACKTEST_ONLY for rule in rules)
