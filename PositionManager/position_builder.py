from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config import StrategyConfig
from daily_decision_engine import evaluate_daily_scale_in, scale_in_allowed
from data_provider import fetch_ohlcv, today_yyyymmdd
from stage_rules import bullish_rebound_confirmed
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

        # V3: CONFIRMED itself is enough for a small starter position.
        if not future.empty:
            first_bar = future.iloc[0]
            actual_trigger_date = future.index[0].strftime("%Y%m%d")
            actual_trigger_price = float(first_bar["Open"])
            stage1_reference = actual_trigger_price
            stage1_status = "TRIGGERED_HISTORY"
            decision_name = "STAGE1_TRIGGERED_HISTORY"
            decision_reason = "CONFIRMED_NEXT_OPEN"
        else:
            actual_trigger_date = ""
            actual_trigger_price = np.nan
            stage1_reference = signal_close
            stage1_status = "NEXT_OPEN_PENDING"
            decision_name = "STAGE1_NEXT_OPEN_PENDING"
            decision_reason = "CONFIRMED_NEXT_OPEN"

        stop_history = history if future.empty else ohlcv.loc[ohlcv.index < future.index[0]]
        stop = initial_stop_price(
            history=stop_history,
            stage1_price=stage1_reference,
            lookback_bars=cfg.structural_lookback_bars,
            structural_buffer_pct=cfg.structural_stop_buffer_pct,
            max_stop_pct=cfg.max_stop_pct,
        )

        evaluation_date = ""
        decision_score = np.nan
        daily_return_pct = np.nan
        signal_gain_pct = np.nan
        volume_ratio_20 = np.nan
        ma20_distance_pct = np.nan
        scale_in_decision = "WAIT_FOR_CLOSE_CONFIRMATION"
        scale_in_reason = "NO_COMPLETED_POST_SIGNAL_BAR"
        add_confirmation = False

        if not future.empty:
            latest_date_idx = future.index[-1]
            history_today = ohlcv.loc[ohlcv.index <= latest_date_idx]
            scale_decision = evaluate_daily_scale_in(
                history=history_today,
                signal_bar=signal_bar,
                structural_stop=stop,
                signal_close=signal_close,
                bars_since_signal=len(future),
                cfg=cfg,
            )
            evaluation_date = scale_decision.evaluation_date
            decision_score = scale_decision.score.total_score
            daily_return_pct = scale_decision.score.daily_return_pct
            signal_gain_pct = scale_decision.score.signal_gain_pct
            volume_ratio_20 = scale_decision.score.volume_ratio_20
            ma20_distance_pct = scale_decision.score.ma20_distance_pct
            scale_in_decision = scale_decision.decision
            scale_in_reason = scale_decision.reason

            if len(future) >= 2:
                add_confirmation = (
                    scale_in_allowed(scale_decision, cfg.stage2_min_daily_score)
                    and bullish_rebound_confirmed(future.iloc[-1], future.iloc[-2])
                )
                if add_confirmation:
                    scale_in_decision = "ADD_NEXT_OPEN"
                    scale_in_reason = "SCORE_AND_BULLISH_REBOUND_CONFIRMED"

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
            "stage1_entry_rule": "CONFIRMED_THEN_NEXT_TRADING_DAY_OPEN",
            "stage1_reference_price": stage1_reference,
            "stage1_status": stage1_status,
            "actual_trigger_date": actual_trigger_date,
            "actual_trigger_open": actual_trigger_price,
            "scale_in_decision": scale_in_decision,
            "scale_in_reason": scale_in_reason,
            "add_confirmation": add_confirmation,
            "stage2_weight_pct": cfg.stage2_weight * 100.0,
            "stage2_entry_rule": (
                f"PRIOR_DAY_SCORE>={cfg.stage2_min_daily_score:.0f} + "
                "BULLISH + CLOSE_ABOVE_PREV_HIGH + CLOSE_ABOVE_MA5, THEN NEXT_OPEN"
            ),
            "stage2_target_price": np.nan,
            "stage3_weight_pct": cfg.stage3_weight * 100.0,
            "stage3_entry_rule": (
                f"AFTER_STAGE2, NEW_PRIOR_DAY_SCORE>={cfg.stage3_min_daily_score:.0f} + "
                "NEW_BULLISH_BREAKOUT_CONFIRMATION, THEN NEXT_OPEN"
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
