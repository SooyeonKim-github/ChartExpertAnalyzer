from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config import StrategyConfig
from daily_decision_engine import (
    decision_log_row,
    evaluate_daily_entry,
    evaluate_daily_scale_in,
    scale_in_allowed,
)
from data_provider import fetch_ohlcv, today_yyyymmdd
from models import BacktestResult, Fill
from performance_tracker import summarize_backtests
from stage_rules import (
    stage2_fill_price,
    stage2_limit_price,
    stage2_touched,
    stage3_rebound_confirmed,
)
from stop_loss import initial_stop_price, stop_fill_price


def _num(value):
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_text(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y%m%d")


def _buy_price(price: float, slippage_bps: float) -> float:
    return float(price) * (1.0 + slippage_bps / 10_000.0)


def _sell_price(price: float, slippage_bps: float) -> float:
    return float(price) * (1.0 - slippage_bps / 10_000.0)


def _add_fill(
    fills: list[Fill],
    stage: int,
    date: pd.Timestamp,
    price: float,
    weight: float,
    cfg: StrategyConfig,
) -> None:
    fill_price = _buy_price(price, cfg.slippage_bps)
    capital = cfg.planned_capital * weight
    quantity = capital / fill_price
    fills.append(Fill(
        stage=stage,
        date=date.strftime("%Y%m%d"),
        price=fill_price,
        weight=weight,
        quantity=quantity,
    ))


def _weighted_average(fills: list[Fill]) -> tuple[float, float, float]:
    invested_weight = sum(fill.weight for fill in fills)
    qty = sum(fill.quantity for fill in fills)
    cost = sum(fill.price * fill.quantity for fill in fills)
    avg = cost / qty if qty > 0 else np.nan
    return invested_weight, qty, avg


def _finish_no_entry(result: BacktestResult, status: str, reason: str) -> None:
    result.trade_status = status
    result.entry_cancel_reason = reason
    result.strategy_return_on_planned_capital_pct = 0.0
    if result.baseline_d20_pct is not None:
        result.alpha_vs_baseline_d20_pct = -float(result.baseline_d20_pct)


def _simulate_row(
    row: pd.Series,
    ohlcv: pd.DataFrame,
    cfg: StrategyConfig,
) -> tuple[BacktestResult, list[dict]]:
    signal_date = _date_text(row.get("signal_date"))
    result = BacktestResult(
        signal_date=signal_date,
        analyzer=str(row.get("analyzer", "")),
        ticker=str(row.get("ticker", "")).replace(".0", "").zfill(6),
        name=str(row.get("name", "")),
        status=str(row.get("status", "")),
        score=_num(row.get("score")),
        timing_score=_num(row.get("timing_score")),
        baseline_d20_pct=_num(row.get("D+20_Pct")),
    )
    logs: list[dict] = []

    signal_dt = pd.to_datetime(signal_date, format="%Y%m%d", errors="coerce")
    if pd.isna(signal_dt) or ohlcv.empty:
        result.trade_status = "NO_DATA"
        return result, logs

    history = ohlcv.loc[ohlcv.index <= signal_dt].copy()
    future = ohlcv.loc[ohlcv.index > signal_dt].copy()
    if history.empty:
        result.trade_status = "NO_SIGNAL_BAR"
        return result, logs
    if future.empty:
        result.trade_status = "NO_FUTURE_BAR"
        return result, logs

    signal_bar = history.iloc[-1]
    signal_close = float(signal_bar["Close"])
    provisional_stop = initial_stop_price(
        history=history,
        stage1_price=signal_close,
        lookback_bars=cfg.structural_lookback_bars,
        structural_buffer_pct=cfg.structural_stop_buffer_pct,
        max_stop_pct=cfg.max_stop_pct,
    )
    result.initial_stop_price = provisional_stop

    fills: list[Fill] = []
    pending_stage1 = not cfg.use_daily_entry_gate
    stage2_allowed_next = False
    stage2_filled = False
    stage3_filled = False
    stage3_pending = False
    scale_in_cancelled = False
    stage2_fill_holding_bar: int | None = None
    hard_stop = provisional_stop
    stage2_target: float | None = None
    trailing_stop: float | None = None
    peak_close: float | None = None
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    exit_reason = ""
    holding_bars = 0
    max_high: float | None = None
    min_low: float | None = None

    loop_bars = min(
        len(future),
        cfg.entry_watch_bars + cfg.max_holding_bars + cfg.stage3_window_bars + 5,
    )

    for pos in range(loop_bars):
        bar_date = future.index[pos]
        bar = future.iloc[pos]
        just_entered = False

        # A READY_BUY decision is made only with the prior close. The fill is next open.
        if not fills and pending_stage1:
            _add_fill(fills, 1, bar_date, float(bar["Open"]), cfg.stage1_weight, cfg)
            result.stage1_date = fills[-1].date
            result.stage1_price = fills[-1].price
            result.wait_bars_before_entry = pos
            just_entered = True
            holding_bars = 1

            pre_entry_history = ohlcv.loc[ohlcv.index < bar_date]
            hard_stop = initial_stop_price(
                history=pre_entry_history,
                stage1_price=fills[-1].price,
                lookback_bars=cfg.structural_lookback_bars,
                structural_buffer_pct=cfg.structural_stop_buffer_pct,
                max_stop_pct=cfg.max_stop_pct,
            )
            stage2_target = stage2_limit_price(fills[-1].price, cfg.stage2_pullback_pct)
            result.initial_stop_price = hard_stop
            result.stage2_target = stage2_target
            pending_stage1 = False
            max_high = float(bar["High"])
            min_low = float(bar["Low"])

            if not cfg.use_daily_entry_gate:
                result.entry_validation_date = signal_date
                result.entry_validation_score = None
                result.entry_decision = "LEGACY_D1_OPEN"
                result.entry_decision_reason = "DAILY_GATE_DISABLED"

        if fills:
            if not just_entered:
                holding_bars += 1

            max_high = max(max_high if max_high is not None else float(bar["High"]), float(bar["High"]))
            min_low = min(min_low if min_low is not None else float(bar["Low"]), float(bar["Low"]))

            # Stage 3 was approved using yesterday's close, so it can fill at today's open.
            if stage3_pending and not stage3_filled and not scale_in_cancelled:
                _add_fill(fills, 3, bar_date, float(bar["Open"]), cfg.stage3_weight, cfg)
                result.stage3_date = fills[-1].date
                result.stage3_price = fills[-1].price
                stage3_filled = True
                stage3_pending = False

            # Existing position risk is checked before any intraday Stage 2 limit fill.
            active_stop = hard_stop if trailing_stop is None else max(hard_stop, trailing_stop)
            stopped_at = stop_fill_price(bar, active_stop)
            if stopped_at is not None:
                exit_date = bar_date
                exit_price = _sell_price(stopped_at, cfg.slippage_bps)
                exit_reason = (
                    "TRAILING_STOP"
                    if trailing_stop is not None and active_stop == trailing_stop
                    else "HARD_STOP"
                )
                break

            if (
                not stage2_filled
                and not scale_in_cancelled
                and stage2_allowed_next
                and holding_bars <= cfg.stage2_window_bars
                and stage2_target is not None
                and stage2_touched(bar, stage2_target)
            ):
                _add_fill(
                    fills,
                    2,
                    bar_date,
                    stage2_fill_price(bar, stage2_target),
                    cfg.stage2_weight,
                    cfg,
                )
                result.stage2_date = fills[-1].date
                result.stage2_price = fills[-1].price
                stage2_filled = True
                stage2_fill_holding_bar = holding_bars

            invested_weight, total_qty, avg_entry = _weighted_average(fills)
            if total_qty > 0:
                close = float(bar["Close"])
                if close >= avg_entry * (1.0 + cfg.trailing_activate_pct):
                    peak_close = max(peak_close or close, close)
                    trailing_stop = peak_close * (1.0 - cfg.trailing_stop_pct)
                elif peak_close is not None:
                    peak_close = max(peak_close, close)
                    trailing_stop = peak_close * (1.0 - cfg.trailing_stop_pct)

            if holding_bars >= cfg.max_holding_bars:
                exit_date = bar_date
                exit_price = _sell_price(float(bar["Close"]), cfg.slippage_bps)
                exit_reason = "D20_TIME_EXIT"
                break

            # Re-score at today's close. This decision can only affect tomorrow or later.
            history_today = ohlcv.loc[ohlcv.index <= bar_date]
            scale_decision = evaluate_daily_scale_in(
                history=history_today,
                signal_bar=signal_bar,
                structural_stop=hard_stop,
                signal_close=signal_close,
                bars_since_signal=pos + 1,
                cfg=cfg,
            )
            logs.append(decision_log_row(
                signal_date=signal_date,
                analyzer=result.analyzer,
                ticker=result.ticker,
                name=result.name,
                position_stage=len(fills),
                decision=scale_decision,
            ))

            if scale_decision.score.hard_cancel_reason:
                scale_in_cancelled = True
                if not result.scale_in_cancel_reason:
                    result.scale_in_cancel_reason = scale_decision.score.hard_cancel_reason

            stage2_allowed_next = (
                not stage2_filled
                and not scale_in_cancelled
                and scale_in_allowed(scale_decision, cfg.stage2_min_daily_score)
            )

            if (
                stage2_filled
                and not stage3_filled
                and not stage3_pending
                and not scale_in_cancelled
                and pos >= 1
                and stage2_fill_holding_bar is not None
                and holding_bars - stage2_fill_holding_bar <= cfg.stage3_window_bars
                and scale_in_allowed(scale_decision, cfg.stage3_min_daily_score)
                and stage3_rebound_confirmed(bar, future.iloc[pos - 1])
                and pos + 1 < loop_bars
            ):
                stage3_pending = True
            continue

        # No position yet: observe D+1, D+2, ... closes and decide whether tomorrow is buyable.
        history_today = ohlcv.loc[ohlcv.index <= bar_date]
        entry_decision = evaluate_daily_entry(
            history=history_today,
            signal_bar=signal_bar,
            structural_stop=provisional_stop,
            signal_close=signal_close,
            bars_since_signal=pos + 1,
            cfg=cfg,
        )
        logs.append(decision_log_row(
            signal_date=signal_date,
            analyzer=result.analyzer,
            ticker=result.ticker,
            name=result.name,
            position_stage=0,
            decision=entry_decision,
        ))
        result.entry_validation_date = entry_decision.evaluation_date
        result.entry_validation_score = entry_decision.score.total_score
        result.entry_decision = entry_decision.decision
        result.entry_decision_reason = entry_decision.reason

        if entry_decision.decision == "READY_BUY":
            if pos + 1 < loop_bars:
                pending_stage1 = True
            else:
                result.trade_status = "READY_BUY_NO_NEXT_BAR"
            continue
        if entry_decision.decision == "CANCEL":
            _finish_no_entry(result, "ENTRY_CANCELLED", entry_decision.reason)
            break
        if entry_decision.decision == "EXPIRED":
            _finish_no_entry(result, "SIGNAL_EXPIRED", entry_decision.reason)
            break

    invested_weight, total_qty, avg_entry = _weighted_average(fills)
    result.invested_weight = invested_weight
    result.avg_entry_price = float(avg_entry) if pd.notna(avg_entry) else None

    if pd.notna(avg_entry) and avg_entry > 0 and max_high is not None and min_low is not None:
        result.max_favorable_excursion_pct = (max_high / avg_entry - 1.0) * 100.0
        result.max_adverse_excursion_pct = (min_low / avg_entry - 1.0) * 100.0

    if exit_date is not None and exit_price is not None and total_qty > 0:
        invested_capital = cfg.planned_capital * invested_weight
        proceeds = total_qty * exit_price
        pnl = proceeds - invested_capital
        position_return = pnl / invested_capital * 100.0 if invested_capital > 0 else np.nan
        strategy_return = pnl / cfg.planned_capital * 100.0
        result.exit_date = exit_date.strftime("%Y%m%d")
        result.exit_price = exit_price
        result.exit_reason = exit_reason
        result.trade_status = "CLOSED"
        result.position_return_pct = float(position_return)
        result.strategy_return_on_planned_capital_pct = float(strategy_return)
        result.bars_held = holding_bars
        if result.baseline_d20_pct is not None:
            result.alpha_vs_baseline_d20_pct = float(strategy_return - result.baseline_d20_pct)
    elif total_qty > 0:
        result.trade_status = "OPEN_INCOMPLETE"
        if loop_bars > 0:
            latest = future.iloc[loop_bars - 1]
            mark = _sell_price(float(latest["Close"]), cfg.slippage_bps)
            invested_capital = cfg.planned_capital * invested_weight
            pnl = total_qty * mark - invested_capital
            result.position_return_pct = pnl / invested_capital * 100.0 if invested_capital > 0 else None
            result.strategy_return_on_planned_capital_pct = pnl / cfg.planned_capital * 100.0
            result.bars_held = holding_bars
            if result.baseline_d20_pct is not None:
                result.alpha_vs_baseline_d20_pct = (
                    result.strategy_return_on_planned_capital_pct - result.baseline_d20_pct
                )
    elif not result.trade_status:
        result.trade_status = "WATCHING_INCOMPLETE"
        result.strategy_return_on_planned_capital_pct = 0.0
        if result.baseline_d20_pct is not None:
            result.alpha_vs_baseline_d20_pct = -float(result.baseline_d20_pct)

    return result, logs


def run_range_backtest(
    input_path: Path,
    output_dir: Path,
    cfg: StrategyConfig,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    signals = pd.read_csv(input_path, encoding="utf-8-sig", dtype={"ticker": str})
    if signals.empty:
        output_dir.mkdir(parents=True, exist_ok=True)
        empty = pd.DataFrame()
        empty.to_csv(output_dir / "position_backtest.csv", index=False, encoding="utf-8-sig")
        empty.to_csv(output_dir / "daily_decisions.csv", index=False, encoding="utf-8-sig")
        summary = summarize_backtests(empty)
        summary.to_csv(output_dir / "position_backtest_summary.csv", index=False, encoding="utf-8-sig")
        return empty, summary

    start_dt = pd.to_datetime(start, format="%Y%m%d")
    end_dt = pd.to_datetime(end, format="%Y%m%d")
    fetch_start = (start_dt - timedelta(days=60)).strftime("%Y%m%d")
    forward_end = min(
        end_dt + timedelta(days=160),
        pd.to_datetime(today_yyyymmdd(), format="%Y%m%d"),
    ).strftime("%Y%m%d")

    ticker_series = (
        signals["ticker"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    )
    grouped = {ticker: signals.loc[ticker_series.eq(ticker)].copy() for ticker in ticker_series.unique()}

    results = []
    daily_logs: list[dict] = []
    total = len(grouped)
    for i, (ticker, group) in enumerate(sorted(grouped.items()), 1):
        print(f"[POSITION] {i}/{total} {ticker} {fetch_start}~{forward_end}")
        ohlcv = fetch_ohlcv(ticker, fetch_start, forward_end)
        for _, row in group.iterrows():
            row = row.copy()
            row["ticker"] = ticker
            result, logs = _simulate_row(row, ohlcv, cfg)
            results.append(result.to_dict())
            daily_logs.extend(logs)

    detail = pd.DataFrame(results)
    decisions = pd.DataFrame(daily_logs)
    summary = summarize_backtests(detail)
    output_dir.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output_dir / "position_backtest.csv", index=False, encoding="utf-8-sig")
    decisions.to_csv(output_dir / "daily_decisions.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(output_dir / "position_backtest_summary.csv", index=False, encoding="utf-8-sig")
    return detail, summary
