from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_backtests(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "analyzer", "count", "entered_count", "closed_count",
        "entry_cancelled_count", "expired_count", "entry_rate_pct", "win_rate_pct",
        "avg_strategy_return_pct", "median_strategy_return_pct",
        "avg_position_return_pct", "avg_invested_weight_pct",
        "avg_baseline_d20_pct", "avg_alpha_vs_baseline_d20_pct",
        "cancelled_avg_baseline_d20_pct",
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
        entered = group[group["invested_weight"].fillna(0) > 0]
        cancelled = group[group["trade_status"].astype(str).eq("ENTRY_CANCELLED")]
        expired = group[group["trade_status"].astype(str).eq("SIGNAL_EXPIRED")]
        closed_returns = closed["strategy_return_on_planned_capital_pct"].dropna()
        strategy_returns = group["strategy_return_on_planned_capital_pct"].dropna()
        baseline = group["baseline_d20_pct"].dropna()
        alpha = group["alpha_vs_baseline_d20_pct"].dropna()
        cancelled_baseline = pd.concat([
            cancelled["baseline_d20_pct"], expired["baseline_d20_pct"]
        ]).dropna()

        rows.append({
            "analyzer": analyzer,
            "count": int(len(group)),
            "entered_count": int(len(entered)),
            "closed_count": int(len(closed)),
            "entry_cancelled_count": int(len(cancelled)),
            "expired_count": int(len(expired)),
            "entry_rate_pct": float(len(entered) / len(group) * 100.0) if len(group) else np.nan,
            "win_rate_pct": float((closed_returns > 0).mean() * 100.0) if len(closed_returns) else np.nan,
            "avg_strategy_return_pct": float(strategy_returns.mean()) if len(strategy_returns) else np.nan,
            "median_strategy_return_pct": float(strategy_returns.median()) if len(strategy_returns) else np.nan,
            "avg_position_return_pct": float(entered["position_return_pct"].mean()) if len(entered) else np.nan,
            "avg_invested_weight_pct": float(group["invested_weight"].fillna(0).mean() * 100.0),
            "avg_baseline_d20_pct": float(baseline.mean()) if len(baseline) else np.nan,
            "avg_alpha_vs_baseline_d20_pct": float(alpha.mean()) if len(alpha) else np.nan,
            "cancelled_avg_baseline_d20_pct": float(cancelled_baseline.mean()) if len(cancelled_baseline) else np.nan,
            "stop_exit_count": int((closed["exit_reason"] == "HARD_STOP").sum()),
            "trailing_exit_count": int((closed["exit_reason"] == "TRAILING_STOP").sum()),
            "time_exit_count": int((closed["exit_reason"] == "D20_TIME_EXIT").sum()),
        })
    return pd.DataFrame(rows, columns=columns)
