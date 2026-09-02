from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from config import DEFAULT_CONFIG
from daily_decision_engine import evaluate_daily_entry


def _frame(closes: list[float], final_volume: float = 120.0) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-01", periods=len(closes))
    close = pd.Series(closes, index=idx, dtype=float)
    df = pd.DataFrame(index=idx)
    df["Close"] = close
    df["Open"] = close.shift(1).fillna(close.iloc[0]) * 0.999
    df["High"] = np.maximum(df["Open"], df["Close"]) * 1.005
    df["Low"] = np.minimum(df["Open"], df["Close"]) * 0.995
    df["Volume"] = 100.0
    df.iloc[-1, df.columns.get_loc("Volume")] = final_volume
    df["MA5"] = df["Close"].rolling(5, min_periods=1).mean()
    df["MA10"] = df["Close"].rolling(10, min_periods=1).mean()
    df["MA20"] = df["Close"].rolling(20, min_periods=1).mean()
    return df


def test_strong_d1_becomes_ready_buy() -> None:
    closes = list(np.linspace(90.0, 100.0, 25)) + [101.5]
    df = _frame(closes, final_volume=140.0)
    signal_bar = df.iloc[-2].copy()
    signal_bar["High"] = 100.5
    signal_bar["Low"] = 99.0
    df.iloc[-1, df.columns.get_loc("Open")] = 100.0
    df.iloc[-1, df.columns.get_loc("High")] = 102.0
    df.iloc[-1, df.columns.get_loc("Low")] = 99.8
    decision = evaluate_daily_entry(
        history=df,
        signal_bar=signal_bar,
        structural_stop=92.0,
        signal_close=100.0,
        bars_since_signal=1,
        cfg=DEFAULT_CONFIG,
    )
    assert decision.decision == "READY_BUY"
    assert decision.score.total_score >= DEFAULT_CONFIG.entry_buy_score


def test_d1_breakdown_is_cancelled() -> None:
    closes = [100.0] * 25 + [94.0]
    df = _frame(closes, final_volume=200.0)
    signal_bar = df.iloc[-2].copy()
    signal_bar["Low"] = 98.0
    decision = evaluate_daily_entry(
        history=df,
        signal_bar=signal_bar,
        structural_stop=92.0,
        signal_close=100.0,
        bars_since_signal=1,
        cfg=DEFAULT_CONFIG,
    )
    assert decision.decision == "CANCEL"
    assert decision.reason in {"CLOSE_BELOW_SIGNAL_LOW", "DAILY_CRASH", "HIGH_VOLUME_DISTRIBUTION"}


def test_d1_overheat_waits_for_pullback() -> None:
    closes = list(np.linspace(90.0, 100.0, 25)) + [107.0]
    df = _frame(closes, final_volume=150.0)
    signal_bar = df.iloc[-2].copy()
    signal_bar["Low"] = 98.5
    decision = evaluate_daily_entry(
        history=df,
        signal_bar=signal_bar,
        structural_stop=92.0,
        signal_close=100.0,
        bars_since_signal=1,
        cfg=DEFAULT_CONFIG,
    )
    assert decision.decision == "WAIT_PULLBACK"
    assert decision.reason == "CHASE_RISK"


def test_entry_window_expires_after_ten_observation_bars() -> None:
    closes = [100.0] * 30
    df = _frame(closes, final_volume=100.0)
    signal_bar = df.iloc[-2].copy()
    signal_bar["Low"] = 99.0
    decision = evaluate_daily_entry(
        history=df,
        signal_bar=signal_bar,
        structural_stop=92.0,
        signal_close=100.0,
        bars_since_signal=11,
        cfg=DEFAULT_CONFIG,
    )
    assert decision.decision == "EXPIRED"
