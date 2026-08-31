from dynamic_chart_analyzer import StrategyConfig, build_entry_plan
from dynamic_chart_analyzer.position_manager import PositionState


def test_10m_split_is_1_2_7():
    cfg = StrategyConfig(total_capital=10_000_000)
    plan = build_entry_plan(cfg)
    assert plan.stage1_amount == 1_000_000
    assert plan.stage2_amount == 2_000_000
    assert plan.stage3_amount == 7_000_000
    assert plan.total_amount == 10_000_000
    assert not plan.risk_capped


def test_optional_two_percent_risk_cap():
    cfg = StrategyConfig(total_capital=10_000_000, use_two_percent_risk_cap=True)
    plan = build_entry_plan(cfg, entry_price=100_000, stop_price=96_000)
    assert round(plan.capital_base) == 5_000_000
    assert round(plan.stage1_amount) == 500_000
    assert round(plan.stage2_amount) == 1_000_000
    assert round(plan.stage3_amount) == 3_500_000
    assert plan.risk_capped


def test_stage_progression_must_be_sequential():
    cfg = StrategyConfig(total_capital=10_000_000)
    plan = build_entry_plan(cfg)
    state = PositionState()
    assert state.enter_stage("LONG", 2, "d0", 100, plan) is None
    assert state.enter_stage("LONG", 1, "d1", 100, plan) is not None
    assert state.enter_stage("LONG", 3, "d2", 110, plan) is None
    assert state.enter_stage("LONG", 2, "d3", 110, plan) is not None
    assert state.enter_stage("LONG", 3, "d4", 120, plan) is not None
    assert round(state.invested_amount) == 10_000_000


def test_full_entry_then_1_2_7_exit_realizes_profit():
    cfg = StrategyConfig(total_capital=10_000_000)
    plan = build_entry_plan(cfg)
    state = PositionState()
    state.enter_stage("LONG", 1, "d1", 100, plan)
    state.enter_stage("LONG", 2, "d2", 100, plan)
    state.enter_stage("LONG", 3, "d3", 100, plan)
    state.exit_part(1, "e1", 110)
    state.exit_part(2, "e2", 120)
    state.exit_part(3, "e3", 130)
    assert state.side is None
    assert state.realized_pnl_krw > 0


def test_stage_ratios_are_fixed_to_1_2_7():
    cfg = StrategyConfig(total_capital=10_000_000)
    assert (cfg.stage1_ratio, cfg.stage2_ratio, cfg.stage3_ratio) == (0.10, 0.20, 0.70)

    try:
        StrategyConfig(stage1_ratio=0.11)
    except TypeError:
        pass
    else:
        raise AssertionError("Stage ratios must not be configurable; this analyzer is fixed at 1:2:7")
