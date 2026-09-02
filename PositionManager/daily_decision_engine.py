from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config import StrategyConfig
from daily_score import DailyScore, score_daily_state


@dataclass
class DailyDecision:
    evaluation_date: str
    decision: str
    reason: str
    bars_since_signal: int
    score: DailyScore

    def to_dict(self) -> dict:
        row = {
            "evaluation_date": self.evaluation_date,
            "decision": self.decision,
            "decision_reason": self.reason,
            "bars_since_signal": self.bars_since_signal,
        }
        row.update(self.score.to_dict())
        return row


def evaluate_daily_entry(
    history: pd.DataFrame,
    signal_bar: pd.Series,
    structural_stop: float,
    signal_close: float,
    bars_since_signal: int,
    cfg: StrategyConfig,
) -> DailyDecision:
    score = score_daily_state(
        history=history,
        signal_bar=signal_bar,
        structural_stop=structural_stop,
        signal_close=signal_close,
        cfg=cfg,
    )
    evaluation_date = history.index[-1].strftime("%Y%m%d")

    if score.hard_cancel_reason:
        return DailyDecision(
            evaluation_date=evaluation_date,
            decision="CANCEL",
            reason=score.hard_cancel_reason,
            bars_since_signal=bars_since_signal,
            score=score,
        )

    if bars_since_signal >= cfg.entry_watch_bars:
        return DailyDecision(
            evaluation_date=evaluation_date,
            decision="EXPIRED",
            reason="ENTRY_WINDOW_EXPIRED",
            bars_since_signal=bars_since_signal,
            score=score,
        )

    overheated = (
        score.signal_gain_pct >= cfg.chase_signal_gain_pct * 100.0
        or (
            score.ma20_distance_pct is not None
            and score.ma20_distance_pct >= cfg.chase_ma20_distance_pct * 100.0
        )
        or score.heat_score <= cfg.min_heat_score_for_entry
    )
    if overheated:
        return DailyDecision(
            evaluation_date=evaluation_date,
            decision="WAIT_PULLBACK",
            reason="CHASE_RISK",
            bars_since_signal=bars_since_signal,
            score=score,
        )

    if score.total_score >= cfg.entry_buy_score:
        return DailyDecision(
            evaluation_date=evaluation_date,
            decision="READY_BUY",
            reason="DAILY_SCORE_READY",
            bars_since_signal=bars_since_signal,
            score=score,
        )

    if score.total_score >= cfg.entry_wait_rebound_score:
        return DailyDecision(
            evaluation_date=evaluation_date,
            decision="WAIT_REBOUND",
            reason="NEEDS_STRONGER_REBOUND",
            bars_since_signal=bars_since_signal,
            score=score,
        )

    if score.total_score >= cfg.entry_cancel_score:
        decision = "WAIT_PULLBACK" if score.signal_gain_pct > 0 else "WAIT_REBOUND"
        return DailyDecision(
            evaluation_date=evaluation_date,
            decision=decision,
            reason="ENTRY_SCORE_NOT_READY",
            bars_since_signal=bars_since_signal,
            score=score,
        )

    return DailyDecision(
        evaluation_date=evaluation_date,
        decision="CANCEL",
        reason="DAILY_SCORE_TOO_LOW",
        bars_since_signal=bars_since_signal,
        score=score,
    )


def scale_in_allowed(decision: DailyDecision, min_score: float) -> bool:
    return (
        not decision.score.hard_cancel_reason
        and decision.score.total_score >= min_score
        and decision.decision not in {"CANCEL", "EXPIRED"}
    )


def decision_log_row(
    *,
    signal_date: str,
    analyzer: str,
    ticker: str,
    name: str,
    position_stage: int,
    decision: DailyDecision,
) -> dict:
    row = {
        "signal_date": signal_date,
        "analyzer": analyzer,
        "ticker": ticker,
        "name": name,
        "position_stage": position_stage,
    }
    row.update(decision.to_dict())
    return row
