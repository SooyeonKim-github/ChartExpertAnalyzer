from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from .models import LeaderResult


ESTABLISHED_STATES = {"LEADER", "PERSISTENT_LEADER"}
ACTIVE_STATES = {"EMERGING", "LEADER", "PERSISTENT_LEADER", "EXHAUSTING"}


@dataclass
class _LifecycleMemory:
    state: str
    days_in_state: int
    observed_days: int
    state_start_date: str
    last_observed_date: str
    promotion_target: str = ""
    promotion_streak: int = 0
    weakness_streak: int = 0
    recovery_streak: int = 0


class LeaderLifecycleEngine:
    """Track leader-stock lifecycle with hysteresis and structural breakdown rules.

    V2.1 adds EmergingLeaderEngine evidence to DISCOVERY -> EMERGING:
    - true emerging candidates require rank/money-flow/RS acceleration.
    - STRONG_EMERGING may fast-track the normal two-day confirmation.
    - once EMERGING, promotion to LEADER is based on established leadership,
      so Rank Velocity is allowed to cool as the stock matures.
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
        high20 = float(close.tail(20).max())
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

    def _readiness(self, item: LeaderResult) -> dict[str, bool]:
        c = self.lcfg
        persistence_score = float(item.leader_persistence_score or 0.0)
        top20_days = int(item.turnover_top20_days_5d or 0)

        persistent = bool(
            item.leader_score >= float(c.get("persistent_min_leader_score", 75.0))
            and item.persistence_available
            and persistence_score >= float(c.get("persistent_min_persistence_score", 70.0))
            and top20_days >= int(c.get("persistent_min_top20_days_5d", 4))
        )
        leader = bool(
            item.leader_score >= float(c.get("leader_min_leader_score", 75.0))
            and item.market_leader_rank <= int(c.get("leader_rank_max", 20))
            and (
                not item.persistence_available
                or top20_days >= int(c.get("leader_min_top20_days_5d", 2))
                or item.leader_persistence_level in {"MEDIUM", "HIGH"}
            )
        )

        legacy_emerging = bool(
            not item.persistence_available
            or top20_days <= int(c.get("emerging_max_top20_days_5d", 2))
            or item.leader_persistence_level in {"MEDIUM", "HIGH"}
        )
        use_emerging_engine = bool(c.get("use_emerging_engine", True) and item.emerging_available)
        emerging_feature_ok = bool(item.true_emerging_flag) if use_emerging_engine else legacy_emerging
        emerging = bool(
            item.leader_score >= float(c.get("emerging_min_leader_score", 72.0))
            and item.market_leader_rank <= int(c.get("emerging_rank_max", 20))
            and not persistent
            and emerging_feature_ok
        )
        discovery = bool(
            item.leader_score >= float(c.get("discovery_min_leader_score", 60.0))
            and item.market_leader_rank <= int(c.get("discovery_rank_max", 50))
        )
        return {
            "persistent": persistent,
            "leader": leader,
            "emerging": emerging,
            "discovery": discovery,
            "emerging_engine_active": use_emerging_engine,
        }

    def _degradation(
        self,
        item: LeaderResult,
        price_ctx: dict[str, float | bool | None],
        prev_state: str,
    ) -> tuple[list[str], list[str]]:
        c = self.lcfg
        drawdown = price_ctx.get("drawdown_20d_pct")
        ret1 = price_ctx.get("return_1d_pct")
        below_ma10 = bool(price_ctx.get("below_ma10", False))
        below_ma20 = bool(price_ctx.get("below_ma20", False))

        exhaustion: list[str] = []
        if item.breakout_exhaustion_risk:
            exhaustion.append("breakout_exhaustion")
        if item.false_breakout_flag:
            exhaustion.append("false_breakout")
        if item.chase_risk >= float(c.get("exhausting_chase_risk", 70.0)):
            exhaustion.append("high_chase_risk")
        if drawdown is not None and drawdown <= -abs(float(c.get("exhausting_drawdown_20d_pct", 7.0))):
            exhaustion.append("20d_drawdown")
        if below_ma10 and ret1 is not None and ret1 < 0:
            exhaustion.append("below_ma10")
        if prev_state in ESTABLISHED_STATES:
            if item.leader_score < float(c.get("exhausting_leader_score", 60.0)):
                exhaustion.append("leader_score_weakness")
            if (
                item.persistence_available
                and float(item.leader_persistence_score or 0.0)
                < float(c.get("exhausting_persistence_score", 45.0))
            ):
                exhaustion.append("persistence_decay")

        broken: list[str] = []
        deep_drawdown = bool(
            drawdown is not None
            and drawdown <= -abs(float(c.get("broken_drawdown_20d_pct", 12.0)))
            and below_ma20
        )
        ma20_selloff = bool(
            below_ma20
            and ret1 is not None
            and ret1 <= float(c.get("broken_return_1d_pct", -3.0))
        )
        failed_breakout = bool(item.false_breakout_flag and below_ma20)
        if deep_drawdown:
            broken.append("deep_drawdown_below_ma20")
        if ma20_selloff:
            broken.append("ma20_break_with_selloff")
        if failed_breakout:
            broken.append("failed_breakout_below_ma20")
        return exhaustion, broken

    @staticmethod
    def _highest_initial_state(readiness: dict[str, bool]) -> tuple[str, str]:
        if readiness["persistent"]:
            return "PERSISTENT_LEADER", "initial_persistent_evidence"
        if readiness["leader"]:
            return "LEADER", "initial_leader_evidence"
        if readiness["emerging"]:
            return "EMERGING", "initial_emerging_evidence"
        if readiness["discovery"]:
            return "DISCOVERY", "initial_discovery_evidence"
        return "DISCOVERY", "initial_below_activation_threshold"

    @staticmethod
    def _promotion_progress(
        previous: _LifecycleMemory,
        target: str,
        required: int,
    ) -> tuple[bool, str, int]:
        if previous.promotion_target == target:
            streak = previous.promotion_streak + 1
        else:
            streak = 1
        return streak >= max(1, required), target, streak

    def _next_state(
        self,
        item: LeaderResult,
        previous: _LifecycleMemory,
        readiness: dict[str, bool],
        exhaustion: list[str],
        broken: list[str],
    ) -> tuple[str, str, str, int, int, int]:
        c = self.lcfg
        state = previous.state
        promotion_target = ""
        promotion_streak = 0
        weakness_streak = previous.weakness_streak
        recovery_streak = previous.recovery_streak

        promotion_confirm = max(1, int(c.get("promotion_confirm_days", 2)))
        demotion_confirm = max(1, int(c.get("demotion_confirm_days", 2)))
        recovery_confirm = max(1, int(c.get("recovery_confirm_days", 2)))
        exhausting_min_flags = max(1, int(c.get("exhausting_min_flags", 2)))
        hard_broken = bool(broken)

        if state == "BROKEN":
            recovery_ready = bool(
                readiness["leader"]
                and item.leader_score >= float(c.get("recovery_min_leader_score", 75.0))
                and not item.lifecycle_below_ma20
            )
            if recovery_ready:
                recovery_streak += 1
                if recovery_streak >= recovery_confirm:
                    return "EMERGING", "confirmed_recovery_after_broken", "", 0, 0, 0
                return "BROKEN", "recovery_confirmation_pending", "", 0, 0, recovery_streak
            return "BROKEN", "broken_state_not_recovered", "", 0, 0, 0

        if state == "EXHAUSTING":
            if hard_broken:
                return "BROKEN", ",".join(broken), "", 0, 0, 0
            recovery_ready = bool(readiness["leader"] and len(exhaustion) < exhausting_min_flags)
            if recovery_ready:
                recovery_streak += 1
                if recovery_streak >= recovery_confirm:
                    return "LEADER", "exhaustion_cleared", "", 0, 0, 0
                return "EXHAUSTING", "exhaustion_recovery_pending", "", 0, 0, recovery_streak
            return "EXHAUSTING", ",".join(exhaustion) or "exhaustion_not_cleared", "", 0, 0, 0

        if state in ESTABLISHED_STATES:
            if hard_broken:
                return "EXHAUSTING", "structural_break_detected:" + ",".join(broken), "", 0, 0, 0
            if len(exhaustion) >= exhausting_min_flags:
                return "EXHAUSTING", ",".join(exhaustion), "", 0, 0, 0

        if state == "DISCOVERY":
            if readiness.get("emerging_engine_active", False):
                if item.strong_emerging_flag and readiness["emerging"]:
                    return "EMERGING", "strong_emerging_fast_track", "", 0, 0, 0
                promotion_ready = readiness["emerging"]
            else:
                promotion_ready = readiness["emerging"] or readiness["leader"] or readiness["persistent"]

            if promotion_ready:
                done, promotion_target, promotion_streak = self._promotion_progress(
                    previous, "EMERGING", promotion_confirm
                )
                if done:
                    reason = (
                        "confirmed_rank_velocity_emerging"
                        if readiness.get("emerging_engine_active", False)
                        else "confirmed_discovery_to_emerging"
                    )
                    return "EMERGING", reason, "", 0, 0, 0
                return (
                    "DISCOVERY",
                    f"emerging_confirmation_pending_{promotion_streak}/{promotion_confirm}",
                    promotion_target,
                    promotion_streak,
                    0,
                    0,
                )
            return "DISCOVERY", "discovery_monitoring", "", 0, 0, 0

        if state == "EMERGING":
            if hard_broken:
                return "BROKEN", ",".join(broken), "", 0, 0, 0
            if readiness["leader"] or readiness["persistent"]:
                done, promotion_target, promotion_streak = self._promotion_progress(
                    previous, "LEADER", promotion_confirm
                )
                if done:
                    return "LEADER", "confirmed_emerging_to_leader", "", 0, 0, 0
                return (
                    "EMERGING",
                    f"leader_confirmation_pending_{promotion_streak}/{promotion_confirm}",
                    promotion_target,
                    promotion_streak,
                    0,
                    0,
                )
            if not readiness["emerging"]:
                weakness_streak += 1
                if weakness_streak >= demotion_confirm:
                    return "DISCOVERY", "confirmed_emerging_weakness", "", 0, 0, 0
                return (
                    "EMERGING",
                    f"emerging_weakness_pending_{weakness_streak}/{demotion_confirm}",
                    "",
                    0,
                    weakness_streak,
                    0,
                )
            return "EMERGING", "emerging_conditions_held", "", 0, 0, 0

        if state == "LEADER":
            persistent_gate = bool(
                readiness["persistent"]
                and (
                    previous.days_in_state >= int(c.get("persistent_min_leader_days", 3))
                    or item.leader_persistence_level == "HIGH"
                )
            )
            if persistent_gate:
                done, promotion_target, promotion_streak = self._promotion_progress(
                    previous, "PERSISTENT_LEADER", promotion_confirm
                )
                if done:
                    return "PERSISTENT_LEADER", "confirmed_leader_to_persistent", "", 0, 0, 0
                return (
                    "LEADER",
                    f"persistent_confirmation_pending_{promotion_streak}/{promotion_confirm}",
                    promotion_target,
                    promotion_streak,
                    0,
                    0,
                )
            if not readiness["leader"]:
                weakness_streak += 1
                if weakness_streak >= demotion_confirm:
                    return "EMERGING", "confirmed_leader_weakness", "", 0, 0, 0
                return (
                    "LEADER",
                    f"leader_weakness_pending_{weakness_streak}/{demotion_confirm}",
                    "",
                    0,
                    weakness_streak,
                    0,
                )
            return "LEADER", "leader_conditions_held", "", 0, 0, 0

        if state == "PERSISTENT_LEADER":
            if not readiness["persistent"]:
                weakness_streak += 1
                if weakness_streak >= demotion_confirm:
                    return "LEADER", "confirmed_persistence_decay", "", 0, 0, 0
                return (
                    "PERSISTENT_LEADER",
                    f"persistence_weakness_pending_{weakness_streak}/{demotion_confirm}",
                    "",
                    0,
                    weakness_streak,
                    0,
                )
            return "PERSISTENT_LEADER", "persistent_conditions_held", "", 0, 0, 0

        return "DISCOVERY", "unknown_state_reset", "", 0, 0, 0

    def enrich(
        self,
        results: list[LeaderResult],
        daily_by_ticker: dict[str, pd.DataFrame],
    ) -> list[LeaderResult]:
        if not results or not self.lcfg.get("enabled", True):
            return results

        out: list[LeaderResult] = []
        reset_days = max(1, int(self.lcfg.get("memory_reset_calendar_days", 10)))

        for item in results:
            ticker = str(item.ticker).zfill(6)
            target_date = pd.Timestamp(item.scan_date).normalize()
            previous = self._memory.get(ticker)

            if previous is not None:
                gap_days = (target_date - pd.Timestamp(previous.last_observed_date).normalize()).days
                if gap_days > reset_days:
                    previous = None

            price_ctx = self._price_context(daily_by_ticker.get(ticker, pd.DataFrame()))
            readiness = self._readiness(item)
            prev_state = previous.state if previous is not None else "UNKNOWN"
            exhaustion, broken = self._degradation(item, price_ctx, prev_state)

            state_item = replace(
                item,
                lifecycle_below_ma20=bool(price_ctx.get("below_ma20", False)),
            )

            if previous is None:
                state, reason = self._highest_initial_state(readiness)
                promotion_target = ""
                promotion_streak = 0
                weakness_streak = 0
                recovery_streak = 0
                changed = False
                days_in_state = 1
                observed_days = 1
                state_start_date = item.scan_date
            else:
                (
                    state,
                    reason,
                    promotion_target,
                    promotion_streak,
                    weakness_streak,
                    recovery_streak,
                ) = self._next_state(
                    state_item,
                    previous,
                    readiness,
                    exhaustion,
                    broken,
                )
                changed = previous.state != state
                observed_days = previous.observed_days + 1
                if changed:
                    days_in_state = 1
                    state_start_date = item.scan_date
                    promotion_target = ""
                    promotion_streak = 0
                    weakness_streak = 0
                    recovery_streak = 0
                else:
                    days_in_state = previous.days_in_state + 1
                    state_start_date = previous.state_start_date

            self._memory[ticker] = _LifecycleMemory(
                state=state,
                days_in_state=days_in_state,
                observed_days=observed_days,
                state_start_date=state_start_date,
                last_observed_date=item.scan_date,
                promotion_target=promotion_target,
                promotion_streak=promotion_streak,
                weakness_streak=weakness_streak,
                recovery_streak=recovery_streak,
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
                    lifecycle_exhaustion_flags=len(exhaustion),
                    lifecycle_broken_flags=len(broken),
                )
            )

        return out
