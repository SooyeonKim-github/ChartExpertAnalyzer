from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .leadership_history import LeadershipHistoryContext
from .models import LeaderResult


class EmergingLeaderEngine:
    """Score stocks that are rapidly becoming market leaders.

    The score is intentionally independent from Leader Score:
      - Rank Velocity               50
      - Trading-value Acceleration  25
      - Relative-strength Accel.    15
      - Freshness                   10

    This distinguishes a newly accelerating TOP10 stock from a stock that has
    already occupied TOP10 for many sessions.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ecfg = cfg.get("emerging_leader", {})

    @staticmethod
    def _lag(series: pd.Series, bars_ago: int) -> float | None:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) <= bars_ago:
            return None
        return float(s.iloc[-bars_ago - 1])

    @staticmethod
    def _period_return(close: pd.Series, bars: int, *, offset: int = 0) -> float | None:
        s = pd.to_numeric(close, errors="coerce").dropna()
        end_pos = len(s) - 1 - int(offset)
        start_pos = end_pos - int(bars)
        if start_pos < 0 or end_pos < 0:
            return None
        start = float(s.iloc[start_pos])
        end = float(s.iloc[end_pos])
        if start <= 0:
            return None
        return (end / start - 1.0) * 100.0

    @staticmethod
    def _rank_component(
        rank_today: float,
        velocity_3d: float | None,
        velocity_5d: float | None,
        acceleration: float | None,
    ) -> float:
        if rank_today <= 10:
            current = 15.0
        elif rank_today <= 20:
            current = 12.0
        elif rank_today <= 50:
            current = 6.0
        else:
            current = 0.0

        v5 = max(0.0, float(velocity_5d or 0.0))
        v3 = max(0.0, float(velocity_3d or 0.0))
        five = min(20.0, v5 / 40.0 * 20.0)
        three = min(10.0, v3 / 20.0 * 10.0)
        accel = max(0.0, float(acceleration or 0.0))
        accel_score = min(5.0, accel / 5.0 * 5.0)
        return round(min(50.0, current + five + three + accel_score), 2)

    @staticmethod
    def _money_flow_component(tv_ratio_5d: float | None, tv_ratio_20d: float | None) -> float:
        ratio = max(float(tv_ratio_5d or 0.0), float(tv_ratio_20d or 0.0) * 0.85)
        if ratio >= 3.0:
            return 25.0
        if ratio >= 2.0:
            return 21.0
        if ratio >= 1.5:
            return 16.0
        if ratio >= 1.2:
            return 10.0
        if ratio >= 1.0:
            return 5.0
        return 0.0

    @staticmethod
    def _rs_component(rs_3d: float | None, rs_5d: float | None, rs_acceleration: float | None) -> float:
        rs3 = float(rs_3d or 0.0)
        if rs3 >= 8.0:
            level = 10.0
        elif rs3 >= 5.0:
            level = 8.0
        elif rs3 >= 3.0:
            level = 6.0
        elif rs3 >= 1.0:
            level = 3.0
        else:
            level = 0.0

        accel = float(rs_acceleration or 0.0)
        if accel >= 3.0:
            accel_score = 5.0
        elif accel >= 1.5:
            accel_score = 4.0
        elif accel >= 0.5:
            accel_score = 2.0
        else:
            accel_score = 0.0
        return round(min(15.0, level + accel_score), 2)

    @staticmethod
    def _freshness_component(top20_days_5d: int) -> float:
        days = int(top20_days_5d)
        if days <= 1:
            return 10.0
        if days == 2:
            return 8.0
        if days == 3:
            return 4.0
        return 0.0

    def enrich(
        self,
        results: list[LeaderResult],
        *,
        history: LeadershipHistoryContext,
        market_period_returns: dict[str, dict[int, float | None]],
    ) -> list[LeaderResult]:
        if not results or not self.ecfg.get("enabled", True) or not history.available:
            return results

        strong_threshold = float(self.ecfg.get("strong_score", 85.0))
        emerging_threshold = float(self.ecfg.get("emerging_score", 70.0))
        watch_threshold = float(self.ecfg.get("watch_score", 55.0))
        max_chase = float(self.ecfg.get("max_chase_risk", 70.0))
        strong_rank_max = int(self.ecfg.get("strong_rank_max", 15))
        strong_velocity_5d = float(self.ecfg.get("strong_rank_velocity_5d", 30.0))

        out: list[LeaderResult] = []
        for item in results:
            ticker = str(item.ticker).zfill(6)
            ranks = history.ranks(ticker)
            pct_ranks = history.rank_percentiles(ticker)
            values = history.trading_values(ticker)
            close = history.closes(ticker)
            if ranks.empty or values.empty or close.empty:
                out.append(item)
                continue

            rank_today = float(ranks.iloc[-1])
            rank_1d = self._lag(ranks, 1)
            rank_3d = self._lag(ranks, 3)
            rank_5d = self._lag(ranks, 5)
            pct_today = float(pct_ranks.iloc[-1]) if not pct_ranks.empty else None
            pct_5d = self._lag(pct_ranks, 5) if not pct_ranks.empty else None

            velocity_1d = (rank_1d - rank_today) if rank_1d is not None else None
            velocity_3d = (rank_3d - rank_today) if rank_3d is not None else None
            velocity_5d = (rank_5d - rank_today) if rank_5d is not None else None
            percentile_velocity_5d = (
                pct_today - pct_5d
                if pct_today is not None and pct_5d is not None
                else None
            )
            per_day_1 = float(velocity_1d or 0.0)
            per_day_5 = float(velocity_5d or 0.0) / 5.0
            rank_acceleration = per_day_1 - per_day_5

            today_value = float(values.iloc[-1])
            prior5 = values.iloc[:-1].tail(5)
            prior20 = values.iloc[:-1].tail(20)
            avg5 = float(prior5.mean()) if not prior5.empty else 0.0
            avg20 = float(prior20.mean()) if not prior20.empty else 0.0
            tv_ratio_5d = today_value / avg5 if avg5 > 0 else None
            tv_ratio_20d = today_value / avg20 if avg20 > 0 else None
            tv_acceleration = (
                float(tv_ratio_5d) - float(tv_ratio_20d)
                if tv_ratio_5d is not None and tv_ratio_20d is not None
                else None
            )

            stock_ret_3d = self._period_return(close, 3)
            stock_ret_5d = self._period_return(close, 5)
            market_map = market_period_returns.get(str(item.market).upper(), {})
            market_ret_3d = market_map.get(3)
            market_ret_5d = market_map.get(5)
            rs_3d = (
                float(stock_ret_3d) - float(market_ret_3d)
                if stock_ret_3d is not None and market_ret_3d is not None
                else stock_ret_3d
            )
            rs_5d = (
                float(stock_ret_5d) - float(market_ret_5d)
                if stock_ret_5d is not None and market_ret_5d is not None
                else stock_ret_5d
            )
            rs_acceleration = (
                float(rs_3d) - float(rs_5d)
                if rs_3d is not None and rs_5d is not None
                else None
            )

            rank_score = self._rank_component(
                rank_today, velocity_3d, velocity_5d, rank_acceleration
            )
            money_score = self._money_flow_component(tv_ratio_5d, tv_ratio_20d)
            rs_score = self._rs_component(rs_3d, rs_5d, rs_acceleration)
            freshness_score = self._freshness_component(item.turnover_top20_days_5d)
            score = round(rank_score + money_score + rs_score + freshness_score, 2)

            if score >= strong_threshold:
                label = "STRONG_EMERGING"
            elif score >= emerging_threshold:
                label = "EMERGING"
            elif score >= watch_threshold:
                label = "WATCH"
            else:
                label = "NOT_EMERGING"

            safe_to_chase = bool(
                item.chase_risk <= max_chase
                and not item.breakout_exhaustion_risk
                and not item.false_breakout_flag
            )
            true_emerging = bool(score >= emerging_threshold and safe_to_chase)
            strong_emerging = bool(
                score >= strong_threshold
                and rank_today <= strong_rank_max
                and float(velocity_5d or 0.0) >= strong_velocity_5d
                and safe_to_chase
            )

            out.append(
                replace(
                    item,
                    emerging_available=True,
                    emerging_leader_score=score,
                    emerging_label=label,
                    emerging_rank_today=round(rank_today, 2),
                    emerging_rank_1d_ago=round(rank_1d, 2) if rank_1d is not None else None,
                    emerging_rank_3d_ago=round(rank_3d, 2) if rank_3d is not None else None,
                    emerging_rank_5d_ago=round(rank_5d, 2) if rank_5d is not None else None,
                    rank_velocity_1d=round(velocity_1d, 2) if velocity_1d is not None else None,
                    rank_velocity_3d=round(velocity_3d, 2) if velocity_3d is not None else None,
                    rank_velocity_5d=round(velocity_5d, 2) if velocity_5d is not None else None,
                    rank_percentile_velocity_5d=(
                        round(percentile_velocity_5d, 2)
                        if percentile_velocity_5d is not None
                        else None
                    ),
                    rank_acceleration=round(rank_acceleration, 2),
                    trading_value_ratio_5d=round(tv_ratio_5d, 3) if tv_ratio_5d is not None else None,
                    trading_value_ratio_20d=round(tv_ratio_20d, 3) if tv_ratio_20d is not None else None,
                    trading_value_acceleration=(
                        round(tv_acceleration, 3) if tv_acceleration is not None else None
                    ),
                    emerging_rs_3d=round(rs_3d, 2) if rs_3d is not None else None,
                    emerging_rs_5d=round(rs_5d, 2) if rs_5d is not None else None,
                    emerging_rs_acceleration=(
                        round(rs_acceleration, 2) if rs_acceleration is not None else None
                    ),
                    emerging_rank_score=rank_score,
                    emerging_money_flow_score=money_score,
                    emerging_rs_score=rs_score,
                    emerging_freshness_score=freshness_score,
                    true_emerging_flag=true_emerging,
                    strong_emerging_flag=strong_emerging,
                )
            )
        return out


class EmergingTransitionAnalyzer:
    """Create validation tables for Emerging -> lifecycle transitions."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ecfg = cfg.get("emerging_leader", {})

    def events(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "true_emerging_flag" not in df.columns:
            return pd.DataFrame()

        work = df.copy()
        work["scan_date"] = work["scan_date"].astype(str)
        work = work.sort_values(["ticker", "scan_date"])
        mask = work["true_emerging_flag"].fillna(False)
        if "lifecycle_state" in work.columns:
            mask &= work["lifecycle_state"].eq("EMERGING")
        events = work[mask].copy()
        if events.empty:
            return events

        horizons = [3, 5, 10]
        rows: list[dict] = []
        grouped = {str(k): g.reset_index(drop=True) for k, g in work.groupby("ticker", sort=False)}
        for _, event in events.iterrows():
            ticker = str(event["ticker"])
            series = grouped.get(ticker)
            if series is None or series.empty:
                continue
            matches = series.index[series["scan_date"].eq(str(event["scan_date"]))].tolist()
            if not matches:
                continue
            pos = matches[0]
            rec = event.to_dict()
            for horizon in horizons:
                future = series.iloc[pos + 1 : pos + 1 + horizon]
                states = set(future.get("lifecycle_state", pd.Series(dtype=str)).dropna().astype(str))
                rec[f"leader_within_{horizon}d"] = bool(
                    {"LEADER", "PERSISTENT_LEADER"}.intersection(states)
                )
                rec[f"persistent_within_{horizon}d"] = "PERSISTENT_LEADER" in states
                rec[f"discovery_within_{horizon}d"] = "DISCOVERY" in states
                rec[f"broken_within_{horizon}d"] = "BROKEN" in states
            rows.append(rec)
        return pd.DataFrame(rows)

    def summary(self, events: pd.DataFrame) -> pd.DataFrame:
        if events.empty:
            return pd.DataFrame()
        row: dict[str, float | int | str] = {"event_count": int(len(events))}
        for horizon in (3, 5, 10):
            for prefix in ("leader", "persistent", "discovery", "broken"):
                col = f"{prefix}_within_{horizon}d"
                if col in events.columns:
                    row[f"{col}_rate"] = round(float(events[col].fillna(False).mean()) * 100.0, 2)
        for col in ("D+5", "D+20", "D+60"):
            if col in events.columns:
                values = pd.to_numeric(events[col], errors="coerce").dropna()
                if not values.empty:
                    row[f"avg_{col}"] = round(float(values.mean()), 2)
                    row[f"median_{col}"] = round(float(values.median()), 2)
                    row[f"win_rate_{col}"] = round(float((values > 0).mean()) * 100.0, 2)
        return pd.DataFrame([row])
