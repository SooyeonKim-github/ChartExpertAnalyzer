from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config import StrategyConfig
from data_provider import fetch_ohlcv, today_yyyymmdd
from stage_rules import stage2_limit_price
from stop_loss import initial_stop_price


def _date_text(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y%m%d")


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

        signal_price = pd.to_numeric(pd.Series([r.get("entry_price")]), errors="coerce").iloc[0]
        known_d1_open = pd.to_numeric(pd.Series([r.get("return_entry_price_d1_open")]), errors="coerce").iloc[0]
        if pd.notna(known_d1_open):
            stage1_anchor = float(known_d1_open)
            stage1_status = "KNOWN_D1_OPEN"
        elif not future.empty:
            stage1_anchor = float(future.iloc[0]["Open"])
            stage1_status = "KNOWN_D1_OPEN"
        elif pd.notna(signal_price):
            stage1_anchor = float(signal_price)
            stage1_status = "NEXT_OPEN_PENDING_USING_SIGNAL_CLOSE"
        elif not history.empty:
            stage1_anchor = float(history.iloc[-1]["Close"])
            stage1_status = "NEXT_OPEN_PENDING_USING_LAST_CLOSE"
        else:
            stage1_anchor = np.nan
            stage1_status = "NO_PRICE"

        if pd.notna(stage1_anchor):
            stage2_target = stage2_limit_price(stage1_anchor, cfg.stage2_pullback_pct)
            stop = initial_stop_price(
                history=history,
                stage1_price=stage1_anchor,
                lookback_bars=cfg.structural_lookback_bars,
                structural_buffer_pct=cfg.structural_stop_buffer_pct,
                max_stop_pct=cfg.max_stop_pct,
            )
        else:
            stage2_target = np.nan
            stop = np.nan

        rows.append({
            "signal_date": signal_date,
            "analyzer": r.get("analyzer", ""),
            "ticker": ticker,
            "name": r.get("name", ""),
            "score": r.get("score", np.nan),
            "timing_score": r.get("timing_score", np.nan),
            "stage1_weight_pct": cfg.stage1_weight * 100.0,
            "stage1_entry_rule": "NEXT_TRADING_DAY_OPEN",
            "stage1_reference_price": stage1_anchor,
            "stage1_status": stage1_status,
            "stage2_weight_pct": cfg.stage2_weight * 100.0,
            "stage2_entry_rule": f"LIMIT_{cfg.stage2_pullback_pct * 100:.2f}%_BELOW_STAGE1",
            "stage2_target_price": stage2_target,
            "stage3_weight_pct": cfg.stage3_weight * 100.0,
            "stage3_entry_rule": "AFTER_STAGE2: BULLISH + CLOSE_ABOVE_PREV_HIGH + CLOSE_ABOVE_MA5, THEN NEXT_OPEN",
            "stop_price": stop,
            "trailing_rule": (
                f"ACTIVATE_AT_+{cfg.trailing_activate_pct * 100:.1f}%_"
                f"THEN_{cfg.trailing_stop_pct * 100:.1f}%_TRAIL"
            ),
            "time_exit_rule": f"D+{cfg.max_holding_bars}_CLOSE",
        })

    out = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")
    return out
