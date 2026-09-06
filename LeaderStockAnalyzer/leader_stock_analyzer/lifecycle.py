from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from .models import LeaderResult


ACTIVE_STATES = {"EMERGING", "LEADER", "PERSISTENT_LEADER", "EXHAUSTING"}


@dataclass
class _LifecycleMemory:
    state: str
    days_in_state: int
    observed_days: int
    state_start_date: str


class LeaderLifecycleEngine:
    """Track the observed lifecycle of a leader stock across scan dates.

    V1 intentionally does not alter Leader Score or CONFIRMED/WATCH/REJECT.
    It adds an independent state machine that can be validated in range
    backtests before lifecycle information is allowed to affect decisions.

    State flow:
        DISCOVERY -> EMERGING -> LEADER -> PERSISTENT_LEADER
                                      -> EXHAUSTING -> BROKEN

    A single-date screen can still infer a state from recent OHLCV and
    PersistenceEngine evidence.  During range scans, reuse one engine instance
    so the previous state and days-in-state are carried forward.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.lcfg = cfg.get("lifecycle", {})
        self._memory: dict[str, _LifecycleMemory] = {}

    @staticmethod
    def _price_context(df: pd.DataFrame) -> dict[str, float | bool | None]:
        if df is None or df.empty or "close" not in df.columns:
            return {
                "drawdown_20d_pct": None,
                "below_ma10": False,
                "below_ma20": False,
                "return_1d_pct": None,
            }

        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        if close.empty:
            return {
                "drawdown_20d_pct": None,
                "below_ma10": False,
                "below_ma20": False,
                "return_1d_pct": None,
            }

        current = float(close.iloc[-1])
        high20 = float(close.tail(20).max()) if len(close) else current
        drawdown = (current / high20 - 1.0) * 100.0 if high20 > 0 else None
        ma10 = float(close.tail(10).mean()) if len(close) >= 10 else None
        ma20 = float(close.tail(20).mean()) if len(close) >= 20 else None
        ret1 = (
            (current / float(close.iloc[-2]) - 1.0) * 100.0
            if len(close) >= 2 and float(close.iloc[-2]) > 0
            else None
        )
        return {
            "drawdown_20d_pct": drawdown,
            "below_ma10": bool(ma10 is not None and current < ma10),
            "below_ma20": bool(ma20 is not None and current < ma20),
            "return_1d_pct": ret1,
        }

    def _candidate_state(
        self,
        item: LeaderResult,
        price_ctx: dict[str, float | bool | None],
        prev_state: str,
    ) -> tuple[str, str, int, int]:
        c = self.lcfg
        persistence_score = float(item.leader_persistence_score or 0.0)
        top20_days = int(item.turnover_top20_days_5d or 0)
        drawdown = price_ctx.get("drawdown_20d_pct")
        ret1 = price_ctx.get("return_1d_pct")
        below_ma10 = bool(price_ctx.get("below_ma10", False))
        below_ma20 = bool(price_ctx.get("below_ma20", False))

        persistent_ready = bool(
            item.leader_score >= float(c.get("persistent_min_leader_score", 75.0))
            and item.persistence_available
            and persistence_score >= float(c.get("persistent_min_persistence_score", 70.0))
            and top20_days >= int(c.get("persistent_min_top20_days_5d", 4))
        )
        leader_ready = bool(
            item.leader_score >= float(c.get("leader_min_leader_score", 75.0))
            and item.market_leader_rank <= int(c.get("leader_rank_max", 20))
            and (
                not item.persistence_available
                or top20_days >= int(c.get("leader_min_top20_days_5d", 2))
                or item.leader_persistence_level in {"MEDIUM", "HIGH"}
            )
        )
        emerging_ready = bool(
            item.leader_score >= float(c.get("emerging_min_leader_score", 72.0))
            and item.market_leader_rank <= int(c.get("emerging_rank_max", 20))
            and not persistent_ready
            and (
                not item.persistence_available
                or top20_days <= int(c.get("emerging_max_top20_days_5d", 2))
            )
        )
        discovery_ready = bool(
            item.leader_score >= float(c.get("discovery_min_leader_score", 60.0))
            and item.market_leader_rank <= int(c.get("discovery_rank_max", 50))
        )

        exhaustion_flags = 0
        exhaustion_reasons: list[str] = []
        if item.breakout_exhaustion_risk:
            exhaustion_flags += 1
            exhaustion_reasons.append("breakout_exhaustion")
        if item.false_breakout_flag:
            exhaustion_flags += 1
            exhaustion_reasons.append("false_breakout")
        if item.chase_risk >= float(c.get("exhausting_chase_risk", 70.0)):
            exhaustion_flags += 1
            exhaustion_reasons.append("high_chase_risk")
        if drawdown is not None and drawdown <= -abs(float(c.get("exhausting_drawdown_20d_pct", 7.0))):
            exhaustion_flags += 1
            exhaustion_reasons.append("20d_drawdown")
        if below_ma10 and ret1 is not None and ret1 < 0:
            exhaustion_flags += 1
            exhaustion_reasons.append("below_ma10")

        broken_flags = 0
        broken_reasons: list[str] = []
        if drawdown is not None and drawdown <= -abs(float(c.get("broken_drawdown_20d_pct", 12.0))):
            broken_flags += 1
            broken_reasons.append("deep_20d_drawdown")
        if below_ma20 and ret1 is not None and ret1 <= float(c.get("broken_return_1d_pct", -3.0)):
            broken_flags += 1
            broken_reasons.append("ma20_break")
        if item.leader_score < float(c.get("broken_leader_score", 60.0)):
            broken_flags += 1
            broken_reasons.append("leader_score_collapse")
        if item.false_breakout_flag and below_ma20:
            broken_flags += 1
            broken_reasons.append("failed_breakout_below_ma20")

        prev_active = prev_state in ACTIVE_STATES
        broken_min_flags = int(c.get("broken_min_flags", 2))
        exhausting_min_flags = int(c.get("exhausting_min_flags", 2))

        if prev_state == "BROKEN":
            recovered = bool(
                leader_ready
                and item.leader_score >= float(c.get("recovery_min_leader_score", 75.0))
                and not below_ma20
            )
            if recovered:
                return "EMERGING", "recovery_after_broken", exhaustion_flags, broken_flags
            return "BROKEN", "broken_state_not_recovered", exhaustion_flags, broken_flags

        if prev_state == "EXHAUSTING" and broken_flags >= 1:
            reason = ",".join(broken_reasons) or "exhausting_breakdown"
            return "BROKEN", reason, exhaustion_flags, broken_flags

        if prev_active and broken_flags >= broken_min_flags:
            reason = ",".join(broken_reasons) or "leadership_broken"
            return "BROKEN", reason, exhaustion_flags, broken_flags

        if prev_state in {"LEADER", "PERSISTENT_LEADER"} and exhaustion_flags >= exhausting_min_flags:
            reason = ",".join(exhaustion_reasons) or "leadership_exhausting"
            return "EXHAUSTING", reason, exhaustion_flags, broken_flags

        if persistent_ready:
            return "PERSISTENT_LEADER", "persistent_rank_and_score", exhaustion_flags, broken_flags
        if leader_ready:
            return "LEADER", "leader_score_rank_persistence", exhaustion_flags, broken_flags
        if emerging_ready:
            return "EMERGING", "strong_but_not_yet_persistent", exhaustion_flags, broken_flags
        if discovery_ready:
            return "DISCOVERY", "early_leadership_candidate", exhaustion_flags, broken_flags

        if prev_active and broken_flags >= 1:
            reason = ",".join(broken_reasons) or "leadership_lost"
            return "BROKEN", reason, exhaustion_flags, broken_flags
        return "DISCOVERY", "below_leader_activation_threshold", exhaustion_flags, broken_flags

    def enrich(
        self,
        results: list[LeaderResult],
        daily_by_ticker: dict[str, pd.DataFrame],
    ) -> list[LeaderResult]:
        if not results or not self.lcfg.get("enabled", True):
            return results

        out: list[LeaderResult] = []
        for item in results:
            ticker = str(item.ticker).zfill(6)
            previous = self._memory.get(ticker)
            prev_state = previous.state if previous is not None else "UNKNOWN"
            price_ctx = self._price_context(daily_by_ticker.get(ticker, pd.DataFrame()))
            state, reason, exhaustion_flags, broken_flags = self._candidate_state(
                item,
                price_ctx,
                prev_state,
            )

            changed = bool(previous is not None and previous.state != state)
            if previous is None:
                days_in_state = 1
                observed_days = 1
                state_start_date = item.scan_date
            else:
                observed_days = previous.observed_days + 1
                if changed:
                    days_in_state = 1
                    state_start_date = item.scan_date
                else:
                    days_in_state = previous.days_in_state + 1
                    state_start_date = previous.state_start_date

            self._memory[ticker] = _LifecycleMemory(
                state=state,
                days_in_state=days_in_state,
                observed_days=observed_days,
                state_start_date=state_start_date,
            )

            out.append(
                replace(
                    item,
                    lifecycle_available=True,
                    lifecycle_state=state,
                    lifecycle_prev_state=prev_state,
                    lifecycle_transition=changed,
                    lifecycle_days_in_state=days_in_state,
                    lifecycle_observed_days=observed_days,
                    lifecycle_state_start_date=state_start_date,
                    lifecycle_reason=reason,
                    lifecycle_drawdown_20d_pct=(
                        round(float(price_ctx["drawdown_20d_pct"]), 2)
                        if price_ctx.get("drawdown_20d_pct") is not None
                        else None
                    ),
                    lifecycle_below_ma20=bool(price_ctx.get("below_ma20", False)),
                    lifecycle_exhaustion_flags=exhaustion_flags,
                    lifecycle_broken_flags=broken_flags,
                )
            )

        return out
