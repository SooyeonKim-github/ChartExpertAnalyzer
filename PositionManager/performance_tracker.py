from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_backtests(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "analyzer", "count", "closed_count", "win_rate_pct",
        "avg_strategy_return_pct", "median_strategy_return_pct",
        "avg_position_return_pct", "avg_invested_weight_pct",
        "avg_baseline_d20_pct", "avg_alpha_vs_baseline_d20_pct",
        "stop_exit_count", "trailing_exit_count", "time_exit_count",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)

    work = df.copy()
    for col in (
        "strategy_return_on_planned_capital_pct",
        "position_return_pct",
        "invested_weight",
        "baseline_d20_pct",
        "alpha_vs_baseline_d20_pct",
    ):
        work[col] = pd.to_numeric(work.get(col), errors="coerce")

    groups = [("ALL", work)] + list(work.groupby("analyzer", dropna=False))
    rows = []
    for analyzer, group in groups:
        closed = group[group["trade_status"].astype(str).eq("CLOSED")]
        returns = closed["strategy_return_on_planned_capital_pct"].dropna()
        rows.append({
            "analyzer": analyzer,
            "count": int(len(group)),
            "closed_count": int(len(closed)),
            "win_rate_pct": float((returns > 0).mean() * 100.0) if len(returns) else np.nan,
            "avg_strategy_return_pct": float(returns.mean()) if len(returns) else np.nan,
            "median_strategy_return_pct": float(returns.median()) if len(returns) else np.nan,
            "avg_position_return_pct": float(closed["position_return_pct"].mean()) if len(closed) else np.nan,
            "avg_invested_weight_pct": float(closed["invested_weight"].mean() * 100.0) if len(closed) else np.nan,
            "avg_baseline_d20_pct": float(closed["baseline_d20_pct"].mean()) if len(closed) else np.nan,
            "avg_alpha_vs_baseline_d20_pct": float(closed["alpha_vs_baseline_d20_pct"].mean()) if len(closed) else np.nan,
            "stop_exit_count": int((closed["exit_reason"] == "HARD_STOP").sum()),
            "trailing_exit_count": int((closed["exit_reason"] == "TRAILING_STOP").sum()),
            "time_exit_count": int((closed["exit_reason"] == "D20_TIME_EXIT").sum()),
        })
    return pd.DataFrame(rows, columns=columns)
