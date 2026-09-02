from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config import StrategyConfig
from daily_decision_engine import evaluate_daily_entry
from data_provider import fetch_ohlcv, today_yyyymmdd
from stage_rules import stage2_limit_price
from stop_loss import initial_stop_price


def _date_text(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y%m%d")


def _num(value):
    try:
        if pd.isna(value):
            return np.nan
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def build_position_plans(input_path: Path, output_path: Path, cfg: StrategyConfig) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    df = pd.read_csv(input_path, encoding="utf-8-sig", dtype={"ticker": str})
    if df.empty:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(output_path, index=False, encoding="utf-8-sig")
        return pd.DataFrame()

    date_col = "scan_date" if "scan_date" in df.columns else "signal_date"
    df[date_col] = df[date_col].map(_date_text)
    latest_date = df[date_col].dropna().astype(str).max()
    selected = df[df[date_col].astype(str).eq(latest_date)].copy()

    rows = []
    for _, r in selected.iterrows():
        ticker = str(r.get("ticker", "")).replace(".0", "").zfill(6)
        signal_date = str(r.get(date_col, ""))
        if not ticker or len(signal_date) != 8:
            continue

        signal_dt = pd.to_datetime(signal_date, format="%Y%m%d")
        start = (signal_dt - timedelta(days=45)).strftime("%Y%m%d")
        end = today_yyyymmdd()
        ohlcv = fetch_ohlcv(ticker, start, end)
        history = ohlcv.loc[ohlcv.index <= signal_dt] if not ohlcv.empty else pd.DataFrame()
        future = ohlcv.loc[ohlcv.index > signal_dt] if not ohlcv.empty else pd.DataFrame()

        signal_price = _num(r.get("entry_price"))
        if history.empty and pd.isna(signal_price):
            rows.append({
                "signal_date": signal_date,
                "analyzer": r.get("analyzer", ""),
                "ticker": ticker,
                "name": r.get("name", ""),
                "daily_entry_decision": "NO_PRICE",
                "daily_entry_reason": "NO_OHLCV",
                "daily_entry_score": np.nan,
            })
            continue

        signal_bar = history.iloc[-1] if not history.empty else pd.Series({
            "Open": signal_price,
            "High": signal_price,
            "Low": signal_price,
            "Close": signal_price,
        })
        signal_close = float(signal_bar["Close"]) if not history.empty else float(signal_price)
        stop = initial_stop_price(
            history=history,
            stage1_price=signal_close,
            lookback_bars=cfg.structural_lookback_bars,
            structural_buffer_pct=cfg.structural_stop_buffer_pct,
            max_stop_pct=cfg.max_stop_pct,
        )

        decision_name = "WATCHING_D1"
        decision_reason = "WAIT_FOR_D1_CLOSE"
        decision_score = np.nan
        evaluation_date = ""
        actual_trigger_date = ""
        actual_trigger_price = np.nan
        last_decision = None

        for pos in range(min(len(future), cfg.entry_watch_bars + 1)):
            bar_date = future.index[pos]
            history_today = ohlcv.loc[ohlcv.index <= bar_date]
            decision = evaluate_daily_entry(
                history=history_today,
                signal_bar=signal_bar,
                structural_stop=stop,
                signal_close=signal_close,
                bars_since_signal=pos + 1,
                cfg=cfg,
            )
            last_decision = decision
            decision_name = decision.decision
            decision_reason = decision.reason
            decision_score = decision.score.total_score
            evaluation_date = decision.evaluation_date

            if decision.decision in {"CANCEL", "EXPIRED"}:
                break
            if decision.decision == "READY_BUY":
                if pos + 1 < len(future):
                    next_bar = future.iloc[pos + 1]
                    actual_trigger_date = future.index[pos + 1].strftime("%Y%m%d")
                    actual_trigger_price = float(next_bar["Open"])
                    decision_name = "ENTRY_TRIGGERED_HISTORY"
                    decision_reason = "PRIOR_READY_BUY_NEXT_OPEN"
                else:
                    decision_name = "BUY_NEXT_OPEN"
                    decision_reason = "LATEST_CLOSE_READY_BUY"
                break

        if last_decision is not None:
            signal_gain_pct = last_decision.score.signal_gain_pct
            volume_ratio_20 = last_decision.score.volume_ratio_20
            ma20_distance_pct = last_decision.score.ma20_distance_pct
            daily_return_pct = last_decision.score.daily_return_pct
        else:
            signal_gain_pct = np.nan
            volume_ratio_20 = np.nan
            ma20_distance_pct = np.nan
            daily_return_pct = np.nan

        if pd.notna(actual_trigger_price):
            stage1_reference = actual_trigger_price
            stage1_status = "TRIGGERED_HISTORY"
        elif decision_name == "BUY_NEXT_OPEN":
            stage1_reference = float(future.iloc[-1]["Close"]) if not future.empty else signal_close
            stage1_status = "NEXT_OPEN_PENDING"
        else:
            stage1_reference = signal_close
            stage1_status = "NOT_APPROVED_YET"

        stage2_target = stage2_limit_price(stage1_reference, cfg.stage2_pullback_pct)

        rows.append({
            "signal_date": signal_date,
            "analyzer": r.get("analyzer", ""),
            "ticker": ticker,
            "name": r.get("name", ""),
            "score": r.get("score", np.nan),
            "timing_score": r.get("timing_score", np.nan),
            "evaluation_date": evaluation_date,
            "daily_entry_decision": decision_name,
            "daily_entry_reason": decision_reason,
            "daily_entry_score": decision_score,
            "daily_return_pct": daily_return_pct,
            "signal_gain_pct": signal_gain_pct,
            "volume_ratio_20": volume_ratio_20,
            "ma20_distance_pct": ma20_distance_pct,
            "stage1_weight_pct": cfg.stage1_weight * 100.0,
            "stage1_entry_rule": "D+1_AND_LATER_DAILY_CLOSE_GATE_THEN_NEXT_OPEN",
            "stage1_reference_price": stage1_reference,
            "stage1_status": stage1_status,
            "actual_trigger_date": actual_trigger_date,
            "actual_trigger_open": actual_trigger_price,
            "stage2_weight_pct": cfg.stage2_weight * 100.0,
            "stage2_entry_rule": (
                f"PRIOR_DAY_SCORE>={cfg.stage2_min_daily_score:.0f} + "
                f"LIMIT_{cfg.stage2_pullback_pct * 100:.2f}%_BELOW_STAGE1"
            ),
            "stage2_target_price": stage2_target,
            "stage3_weight_pct": cfg.stage3_weight * 100.0,
            "stage3_entry_rule": (
                f"PRIOR_DAY_SCORE>={cfg.stage3_min_daily_score:.0f} + "
                "BULLISH + CLOSE_ABOVE_PREV_HIGH + CLOSE_ABOVE_MA5, THEN NEXT_OPEN"
            ),
            "stop_price": stop,
            "trailing_rule": (
                f"ACTIVATE_AT_+{cfg.trailing_activate_pct * 100:.1f}%_"
                f"THEN_{cfg.trailing_stop_pct * 100:.1f}%_TRAIL"
            ),
            "time_exit_rule": f"{cfg.max_holding_bars}_BARS_AFTER_ACTUAL_ENTRY_CLOSE",
        })

    out = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")
    return out
