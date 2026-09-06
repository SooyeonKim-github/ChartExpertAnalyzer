from trend_following_analyzer.rule_catalog import ACTIVE_FILTER,BACKTEST_ONLY,EXPERIMENTAL,LECTURE_CORE,RULE_CATALOG

def test_experimental_rules_do_not_default_to_active_filter():
    rules=[r for r in RULE_CATALOG if r.origin==EXPERIMENTAL]; assert rules and all(r.mode!=ACTIVE_FILTER for r in rules)
def test_lecture_core_has_active_market_and_trend_rules():
    active={r.key for r in RULE_CATALOG if r.origin==LECTURE_CORE and r.mode==ACTIVE_FILTER}; assert {"trend.ma150_position","trend.ma150_slope","market.ma150_position","market.ma150_slope"}.issubset(active)
def test_52w_breadth_is_lecture_core_but_backtest_only():
    r=next(r for r in RULE_CATALOG if r.key=="market.52w_high_breadth"); assert r.origin==LECTURE_CORE and r.mode==BACKTEST_ONLY
def test_intraday_strength_is_lecture_core_but_backtest_only():
    r=next(r for r in RULE_CATALOG if r.key=="market.intraday_strength"); assert r.origin==LECTURE_CORE and r.mode==BACKTEST_ONLY
def test_relative_strength_concept_is_lecture_core_but_backtest_only():
    r=next(r for r in RULE_CATALOG if r.key=="stock.relative_strength"); assert r.origin==LECTURE_CORE and r.mode==BACKTEST_ONLY
def test_prior_advance_concept_is_lecture_core_but_backtest_only():
    r=next(r for r in RULE_CATALOG if r.key=="stock.prior_advance"); assert r.origin==LECTURE_CORE and r.mode==BACKTEST_ONLY
def test_prior_advance_numeric_rules_are_experimental():
    keys={"stock.prior_advance_window_proxy","stock.prior_advance_threshold","stock.prior_advance_ma150_expansion"}; rules=[r for r in RULE_CATALOG if r.key in keys]; assert {r.key for r in rules}==keys and all(r.origin==EXPERIMENTAL and r.mode==BACKTEST_ONLY for r in rules)
