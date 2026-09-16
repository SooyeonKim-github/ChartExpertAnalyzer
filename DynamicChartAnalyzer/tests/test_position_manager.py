from dynamic_chart_analyzer import StrategyConfig, build_entry_plan
from dynamic_chart_analyzer.position_manager import PositionState


def test_10m_entry_split_is_2_6_2():
    cfg = StrategyConfig(total_capital=10_000_000)
    plan = build_entry_plan(cfg)
    assert plan.stage1_amount == 2_000_000
    assert plan.stage2_amount == 6_000_000
    assert plan.stage3_amount == 2_000_000
    assert plan.total_amount == 10_000_000
    assert not plan.risk_capped


def test_optional_two_percent_risk_cap_keeps_2_6_2_entry_split():
    cfg = StrategyConfig(total_capital=10_000_000, use_two_percent_risk_cap=True)
    plan = build_entry_plan(cfg, entry_price=100_000, stop_price=96_000)
    assert round(plan.capital_base) == 5_000_000
    assert round(plan.stage1_amount) == 1_000_000
    assert round(plan.stage2_amount) == 3_000_000
    assert round(plan.stage3_amount) == 1_000_000
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


def test_2_6_2_entry_keeps_original_1_2_7_exit_policy():
    cfg = StrategyConfig(total_capital=10_000_000)
    plan = build_entry_plan(cfg)
    state = PositionState()
    state.enter_stage("LONG", 1, "d1", 100, plan)
    state.enter_stage("LONG", 2, "d2", 100, plan)
    state.enter_stage("LONG", 3, "d3", 100, plan)

    event1 = state.exit_part(1, "e1", 110)
    event2 = state.exit_part(2, "e2", 120)
    event3 = state.exit_part(3, "e3", 130)

    assert event1 is not None and round(event1["remaining_ratio"], 10) == 0.9
    assert event2 is not None and round(event2["remaining_ratio"], 10) == 0.7
    assert event3 is not None and round(event3["remaining_ratio"], 10) == 0.0
    assert state.side is None
    assert state.realized_pnl_krw > 0


def test_stage3_terminal_exit_closes_all_remaining_quantity_without_prior_partial_exits():
    cfg = StrategyConfig(total_capital=10_000_000)
    plan = build_entry_plan(cfg)
    state = PositionState()
    state.enter_stage("LONG", 1, "d1", 100, plan)
    state.enter_stage("LONG", 2, "d2", 100, plan)
    state.enter_stage("LONG", 3, "d3", 100, plan)
    full_quantity = state.total_quantity

    event = state.exit_part(3, "e3", 110)

    assert event is not None
    assert round(event["quantity"], 10) == round(full_quantity, 10)
    assert round(event["remaining_ratio"], 10) == 0.0
    assert state.side is None
    assert state.total_quantity == 0.0


def test_entry_stage_ratios_are_fixed_to_2_6_2():
    cfg = StrategyConfig(total_capital=10_000_000)
    assert (cfg.stage1_ratio, cfg.stage2_ratio, cfg.stage3_ratio) == (0.20, 0.60, 0.20)

    try:
        StrategyConfig(stage1_ratio=0.10)
    except TypeError:
        pass
    else:
        raise AssertionError("Entry stage ratios must not be configurable; this experiment is fixed at 2:6:2")
