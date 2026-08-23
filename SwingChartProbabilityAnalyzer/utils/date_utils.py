from __future__ import annotations

import pandas as pd


def calendar_start_for_history(target_date: str, days: int = 520) -> str:
    return (pd.Timestamp(target_date) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def calendar_end_for_backtest(target_date: str, days: int = 45) -> str:
    return (pd.Timestamp(target_date) + pd.Timedelta(days=days)).strftime("%Y-%m-%d")
