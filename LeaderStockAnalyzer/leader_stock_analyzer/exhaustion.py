from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .leadership_history import LeadershipHistoryContext
from .models import LeaderResult


class ExhaustionRiskEngine:
    """Score leadership rollover before structural breakdown.

    V1.1 deliberately treats overextension as context, not as exhaustion by
    itself. The score emphasizes deterioration from a recent peak:

      - Overextension context            5
      - Momentum rollover               30
      - Distribution / breakout failure 25
      - Money-flow / rank decay          20
      - Price-structure deterioration    20

    The engine is observational only. It does not change Lifecycle, Leader
    Score, Timing Score, or confirmation status.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.xcfg = cfg.get("exhaustion_risk", {})
        self._memory: dict[str, list[dict[str, float | str | None]]] = {}

    @staticmethod
    def _series(df: pd.DataFrame, column: str) -> pd.Series:
        if df is None or df.empty or column not in df.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(df[column], errors="coerce").dropna()

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

    @classmethod
    def _rolling_return_peak(
        cls,
        close: pd.Series,
        *,
        bars: int = 3,
        lookback: int = 10,
    ) -> float | None:
        values: list[float] = []
        for offset in range(max(1, int(lookback))):
            value = cls._period_return(close, bars, offset=offset)
            if value is not None:
                values.append(float(value))
        return max(values) if values else None

    @staticmethod
    def _atr14(df: pd.DataFrame) -> float | None:
        if df is None or df.empty or len(df) < 2:
            return None
        if not {"high", "low", "close"}.issubset(df.columns):
            return None
        high = pd.to_numeric(df["high"], errors="coerce")
        low = pd.to_numeric(df["low"], errors="coerce")
        close = pd.to_numeric(df["close"], errors="coerce")
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        tr = pd.to_numeric(tr, errors="coerce").dropna().tail(14)
        if tr.empty:
            return None
        return float(tr.mean())

    @staticmethod
    def _ma_distance_series(close: pd.Series, window: int) -> pd.Series:
        s = pd.to_numeric(close, errors="coerce").dropna()
        ma = s.rolling(int(window)).mean()
        out = (s / ma - 1.0) * 100.0
        return pd.to_numeric(out, errors="coerce").dropna()

    @classmethod
    def _distance_decay(
        cls,
        close: pd.Series,
        *,
        window: int,
        lookback: int = 5,
    ) -> tuple[float | None, float | None]:
        distance = cls._ma_distance_series(close, window)
        if distance.empty:
            return None, None
        current = float(distance.iloc[-1])
        recent = distance.tail(max(2, int(lookback) + 1))
        peak = float(recent.max())
        return current, max(0.0, peak - current)

    @staticmethod
    def _ma_slope(close: pd.Series, *, window: int, bars: int = 5) -> float | None:
        s = pd.to_numeric(close, errors="coerce").dropna()
        ma = s.rolling(int(window)).mean().dropna()
        if len(ma) <= int(bars):
            return None
        prev = float(ma.iloc[-1 - int(bars)])
        current = float(ma.iloc[-1])
        if prev <= 0:
            return None
        return (current / prev - 1.0) * 100.0

    @staticmethod
    def _prior_peak(
        observations: list[dict[str, float | str | None]],
        key: str,
        lookback: int,
    ) -> float | None:
        values: list[float] = []
        for observation in observations[-max(1, int(lookback)) :]:
            raw = observation.get(key)
            if raw is None:
                continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue
        return max(values) if values else None

    def _history_for(self, ticker: str, scan_date: str) -> list[dict[str, float | str | None]]:
        history = list(self._memory.get(ticker, []))
        if not history:
            return history
        reset_days = max(1, int(self.xcfg.get("memory_reset_calendar_days", 15)))
        try:
            current = pd.Timestamp(scan_date).normalize()
            last = pd.Timestamp(str(history[-1].get("scan_date", ""))).normalize()
            if (current - last).days > reset_days:
                history = []
        except Exception:
            pass
        return history

    def _remember(
        self,
        ticker: str,
        item: LeaderResult,
        current_rs: float | None,
    ) -> None:
        history = self._history_for(ticker, item.scan_date)
        history.append(
            {
                "scan_date": str(item.scan_date),
                "leader_score": float(item.leader_score),
                "rs": float(current_rs) if current_rs is not None else None,
                "persistence_score": (
                    float(item.leader_persistence_score)
                    if item.leader_persistence_score is not None
                    else None
                ),
            }
        )
        keep = max(5, int(self.xcfg.get("history_observations", 10)))
        self._memory[ticker] = history[-keep:]

    @staticmethod
    def _score_overextension(
        *,
        distance_ma20_pct: float | None,
        return_5d: float | None,
        atr_extension: float | None,
        chase_risk: float,
        cap: float,
    ) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        d20 = float(distance_ma20_pct or 0.0)
        r5 = float(return_5d or 0.0)
        atrx = float(atr_extension or 0.0)

        if d20 >= 20:
            score += 2.0
            flags.append("ma20_extreme_extension_context")
        elif d20 >= 12:
            score += 1.0

        if r5 >= 25:
            score += 1.0
            flags.append("five_day_parabolic_context")
        if atrx >= 3.0:
            score += 1.0
            flags.append("atr_extreme_extension_context")
        if chase_risk >= 70:
            score += 1.0
            flags.append("high_chase_context")

        return min(float(cap), score), flags

    @staticmethod
    def _score_rollover(
        *,
        momentum_drop_from_peak: float | None,
        price_momentum_deceleration: float | None,
        leader_score_decay: float | None,
        rs_decay_from_peak: float | None,
        return_1d: float,
        momentum_peak_10d: float | None,
        cap: float,
    ) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        mdrop = float(momentum_drop_from_peak or 0.0)
        pdec = float(price_momentum_deceleration or 0.0)
        ldec = float(leader_score_decay or 0.0)
        rsdec = float(rs_decay_from_peak or 0.0)

        if mdrop >= 15:
            score += 10
            flags.append("momentum_drop_from_peak_extreme")
        elif mdrop >= 10:
            score += 8
            flags.append("momentum_drop_from_peak")
        elif mdrop >= 6:
            score += 5
        elif mdrop >= 3:
            score += 2

        if pdec >= 10:
            score += 5
            flags.append("three_day_momentum_rollover")
        elif pdec >= 5:
            score += 3
        elif pdec >= 2:
            score += 1

        if ldec >= 25:
            score += 8
            flags.append("leader_score_sharp_decay")
        elif ldec >= 15:
            score += 6
            flags.append("leader_score_decay")
        elif ldec >= 8:
            score += 3

        if rsdec >= 8:
            score += 5
            flags.append("rs_decay_from_peak")
        elif rsdec >= 4:
            score += 3
        elif rsdec >= 2:
            score += 1

        if return_1d < 0 and float(momentum_peak_10d or 0.0) >= 10:
            score += 2
            flags.append("negative_day_after_momentum_peak")

        return min(float(cap), score), flags

    @staticmethod
    def _score_distribution(item: LeaderResult, *, cap: float) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []

        if item.false_breakout_flag:
            score += 12
            flags.append("false_breakout")
        if item.breakout_exhaustion_risk:
            score += 10
            flags.append("breakout_exhaustion")

        wick = float(item.upper_wick_ratio or 0.0)
        if wick >= 0.55:
            score += 5
            flags.append("long_upper_wick")
        elif wick >= 0.35:
            score += 3

        clv = item.close_location_value
        if clv is not None:
            if float(clv) <= 0.25:
                score += 4
                flags.append("weak_close_location")
            elif float(clv) <= 0.40:
                score += 2

        if float(item.volume_ratio_20 or 0.0) >= 2.0 and float(item.return_pct or 0.0) < 0:
            score += 5
            flags.append("high_volume_down_day")

        return min(float(cap), score), flags

    @staticmethod
    def _score_money_flow(
        *,
        rank_reversal_3d: float | None,
        rank_reversal_5d: float | None,
        trading_value_decay_ratio: float | None,
        persistence_decay_from_peak: float | None,
        current_persistence_score: float | None,
        cap: float,
    ) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        r3 = float(rank_reversal_3d or 0.0)
        r5 = float(rank_reversal_5d or 0.0)

        if r3 >= 20:
            score += 6
            flags.append("rank_reversal_3d")
        elif r3 >= 10:
            score += 4
        elif r3 >= 5:
            score += 2

        if r5 >= 30:
            score += 5
            flags.append("rank_reversal_5d")
        elif r5 >= 15:
            score += 3
        elif r5 >= 8:
            score += 1

        if trading_value_decay_ratio is not None:
            decay = float(trading_value_decay_ratio)
            if decay <= 0.30:
                score += 6
                flags.append("trading_value_sharp_decay")
            elif decay <= 0.50:
                score += 4
                flags.append("trading_value_decay")
            elif decay <= 0.70:
                score += 2

        pdec = float(persistence_decay_from_peak or 0.0)
        if pdec >= 25:
            score += 4
            flags.append("persistence_decay_from_peak")
        elif pdec >= 15:
            score += 3
        elif pdec >= 8:
            score += 1

        if current_persistence_score is not None and float(current_persistence_score) < 45:
            score += 2
            flags.append("persistence_currently_weak")

        return min(float(cap), score), flags

    @staticmethod
    def _score_structure(
        *,
        distance_ma10_decay_5d: float | None,
        distance_ma20_decay_5d: float | None,
        drawdown_20d_pct: float | None,
        below_ma10: bool,
        below_ma20: bool,
        ma20_slope_5d_pct: float | None,
        cap: float,
    ) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        d10 = float(distance_ma10_decay_5d or 0.0)
        d20 = float(distance_ma20_decay_5d or 0.0)
        dd = float(drawdown_20d_pct or 0.0)

        if d10 >= 10:
            score += 4
            flags.append("ma10_distance_sharp_decay")
        elif d10 >= 6:
            score += 3
        elif d10 >= 3:
            score += 2

        if d20 >= 10:
            score += 5
            flags.append("ma20_distance_sharp_decay")
        elif d20 >= 6:
            score += 4
        elif d20 >= 3:
            score += 2

        if dd <= -12:
            score += 5
            flags.append("deep_20d_drawdown")
        elif dd <= -8:
            score += 4
        elif dd <= -5:
            score += 2

        if below_ma10:
            score += 2
            flags.append("below_ma10")
        if below_ma20:
            score += 4
            flags.append("below_ma20")

        slope = float(ma20_slope_5d_pct or 0.0)
        if slope <= -2:
            score += 2
            flags.append("ma20_slope_down")
        elif slope < 0:
            score += 1

        return min(float(cap), score), flags

    def enrich(
        self,
        results: list[LeaderResult],
        *,
        daily_by_ticker: dict[str, pd.DataFrame],
        history: LeadershipHistoryContext,
    ) -> list[LeaderResult]:
        if not results or not self.xcfg.get("enabled", True):
            return results

        weights = self.xcfg.get("weights", {})
        over_cap = float(weights.get("overextension", 5.0))
        rollover_cap = float(weights.get("momentum_rollover", 30.0))
        distribution_cap = float(weights.get("distribution", 25.0))
        money_cap = float(weights.get("money_flow_decay", 20.0))
        structure_cap = float(weights.get("structure_deterioration", 20.0))

        watch_score = float(self.xcfg.get("watch_score", 35.0))
        high_score = float(self.xcfg.get("high_score", 55.0))
        critical_score = float(self.xcfg.get("critical_score", 75.0))
        memory_lookback = max(2, int(self.xcfg.get("peak_observations", 5)))
        momentum_lookback = max(3, int(self.xcfg.get("momentum_peak_lookback", 10)))

        out: list[LeaderResult] = []
        for item in results:
            ticker = str(item.ticker).zfill(6)
            daily = daily_by_ticker.get(ticker, pd.DataFrame())
            close = self._series(daily, "close")
            if close.empty:
                out.append(item)
                continue

            observations = self._history_for(ticker, item.scan_date)
            current = float(close.iloc[-1])
            distance_ma10, distance_ma10_decay = self._distance_decay(
                close,
                window=10,
                lookback=5,
            )
            distance_ma20, distance_ma20_decay = self._distance_decay(
                close,
                window=20,
                lookback=5,
            )
            ma10 = float(close.tail(10).mean()) if len(close) >= 10 else None
            ma20 = float(close.tail(20).mean()) if len(close) >= 20 else None

            high20 = float(close.tail(20).max())
            drawdown20 = ((current / high20) - 1.0) * 100.0 if high20 > 0 else None

            return_5d = self._period_return(close, 5)
            return_10d = self._period_return(close, 10)
            momentum_3d = self._period_return(close, 3)
            previous_3d = self._period_return(close, 3, offset=3)
            momentum_peak_10d = self._rolling_return_peak(
                close,
                bars=3,
                lookback=momentum_lookback,
            )
            momentum_drop_from_peak = (
                max(0.0, float(momentum_peak_10d) - float(momentum_3d))
                if momentum_peak_10d is not None and momentum_3d is not None
                else None
            )
            price_deceleration = (
                float(previous_3d) - float(momentum_3d)
                if momentum_3d is not None and previous_3d is not None
                else None
            )

            current_rs = (
                float(item.emerging_rs_3d)
                if item.emerging_rs_3d is not None
                else (
                    float(item.market_relative_strength)
                    if item.market_relative_strength is not None
                    else None
                )
            )
            leader_score_peak = self._prior_peak(
                observations,
                "leader_score",
                memory_lookback,
            )
            leader_score_decay = (
                max(0.0, float(leader_score_peak) - float(item.leader_score))
                if leader_score_peak is not None
                else None
            )
            rs_peak = self._prior_peak(observations, "rs", memory_lookback)
            rs_decay_from_peak = (
                max(0.0, float(rs_peak) - float(current_rs))
                if rs_peak is not None and current_rs is not None
                else None
            )
            persistence_peak = self._prior_peak(
                observations,
                "persistence_score",
                memory_lookback,
            )
            persistence_decay_from_peak = (
                max(
                    0.0,
                    float(persistence_peak) - float(item.leader_persistence_score),
                )
                if persistence_peak is not None and item.leader_persistence_score is not None
                else None
            )

            short_rs_deceleration = (
                max(0.0, -float(item.emerging_rs_acceleration))
                if item.emerging_rs_acceleration is not None
                else None
            )

            atr14 = self._atr14(daily)
            atr_extension = (
                (current - float(ma20)) / float(atr14)
                if ma20 is not None and atr14 is not None and atr14 > 0
                else None
            )
            ma10_slope = self._ma_slope(close, window=10, bars=5)
            ma20_slope = self._ma_slope(close, window=20, bars=5)

            ranks = history.ranks(ticker) if history.available else pd.Series(dtype=float)
            values = history.trading_values(ticker) if history.available else pd.Series(dtype=float)
            rank_today = float(ranks.iloc[-1]) if not ranks.empty else float(item.trading_value_rank)
            prior3 = pd.to_numeric(ranks.iloc[:-1].tail(3), errors="coerce").dropna()
            prior5 = pd.to_numeric(ranks.iloc[:-1].tail(5), errors="coerce").dropna()
            rank_reversal_3d = rank_today - float(prior3.min()) if not prior3.empty else None
            rank_reversal_5d = rank_today - float(prior5.min()) if not prior5.empty else None

            trading_value_decay_ratio = None
            if not values.empty:
                today_value = float(values.iloc[-1])
                prior_values = pd.to_numeric(values.iloc[:-1].tail(5), errors="coerce").dropna()
                if not prior_values.empty and float(prior_values.max()) > 0:
                    trading_value_decay_ratio = today_value / float(prior_values.max())

            over_score, over_flags = self._score_overextension(
                distance_ma20_pct=distance_ma20,
                return_5d=return_5d,
                atr_extension=atr_extension,
                chase_risk=float(item.chase_risk or 0.0),
                cap=over_cap,
            )
            rollover_score, rollover_flags = self._score_rollover(
                momentum_drop_from_peak=momentum_drop_from_peak,
                price_momentum_deceleration=price_deceleration,
                leader_score_decay=leader_score_decay,
                rs_decay_from_peak=rs_decay_from_peak,
                return_1d=float(item.return_pct or 0.0),
                momentum_peak_10d=momentum_peak_10d,
                cap=rollover_cap,
            )
            distribution_score, distribution_flags = self._score_distribution(
                item,
                cap=distribution_cap,
            )
            money_score, money_flags = self._score_money_flow(
                rank_reversal_3d=rank_reversal_3d,
                rank_reversal_5d=rank_reversal_5d,
                trading_value_decay_ratio=trading_value_decay_ratio,
                persistence_decay_from_peak=persistence_decay_from_peak,
                current_persistence_score=item.leader_persistence_score,
                cap=money_cap,
            )
            structure_score, structure_flags = self._score_structure(
                distance_ma10_decay_5d=distance_ma10_decay,
                distance_ma20_decay_5d=distance_ma20_decay,
                drawdown_20d_pct=drawdown20,
                below_ma10=bool(ma10 is not None and current < ma10),
                below_ma20=bool(ma20 is not None and current < ma20),
                ma20_slope_5d_pct=ma20_slope,
                cap=structure_cap,
            )

            total_score = round(
                over_score
                + rollover_score
                + distribution_score
                + money_score
                + structure_score,
                2,
            )
            if total_score >= critical_score:
                label = "CRITICAL"
            elif total_score >= high_score:
                label = "HIGH"
            elif total_score >= watch_score:
                label = "WATCH"
            else:
                label = "LOW"

            flags = list(
                dict.fromkeys(
                    over_flags
                    + rollover_flags
                    + distribution_flags
                    + money_flags
                    + structure_flags
                )
            )

            out.append(
                replace(
                    item,
                    exhaustion_risk_available=True,
                    exhaustion_risk_score=total_score,
                    exhaustion_risk_label=label,
                    exhaustion_overextension_score=round(over_score, 2),
                    exhaustion_deceleration_score=round(rollover_score, 2),
                    exhaustion_distribution_score=round(distribution_score, 2),
                    exhaustion_money_flow_decay_score=round(money_score, 2),
                    exhaustion_structure_score=round(structure_score, 2),
                    exhaustion_flags=",".join(flags),
                    exhaustion_return_5d=round(return_5d, 2) if return_5d is not None else None,
                    exhaustion_return_10d=round(return_10d, 2) if return_10d is not None else None,
                    price_momentum_deceleration=(
                        round(price_deceleration, 2) if price_deceleration is not None else None
                    ),
                    rs_deceleration=(
                        round(short_rs_deceleration, 2)
                        if short_rs_deceleration is not None
                        else None
                    ),
                    rank_reversal_3d=round(rank_reversal_3d, 2) if rank_reversal_3d is not None else None,
                    rank_reversal_5d=round(rank_reversal_5d, 2) if rank_reversal_5d is not None else None,
                    trading_value_decay_ratio=(
                        round(trading_value_decay_ratio, 3)
                        if trading_value_decay_ratio is not None
                        else None
                    ),
                    exhaustion_distance_ma10_pct=(
                        round(distance_ma10, 2) if distance_ma10 is not None else None
                    ),
                    exhaustion_distance_ma20_pct=(
                        round(distance_ma20, 2) if distance_ma20 is not None else None
                    ),
                    atr_extension=round(atr_extension, 2) if atr_extension is not None else None,
                    exhaustion_ma10_slope_5d_pct=(
                        round(ma10_slope, 2) if ma10_slope is not None else None
                    ),
                    exhaustion_ma20_slope_5d_pct=(
                        round(ma20_slope, 2) if ma20_slope is not None else None
                    ),
                    exhaustion_drawdown_20d_pct=(
                        round(drawdown20, 2) if drawdown20 is not None else None
                    ),
                    exhaustion_below_ma10=bool(ma10 is not None and current < ma10),
                    exhaustion_below_ma20=bool(ma20 is not None and current < ma20),
                    exhaustion_momentum_3d=(
                        round(momentum_3d, 2) if momentum_3d is not None else None
                    ),
                    exhaustion_momentum_peak_10d=(
                        round(momentum_peak_10d, 2)
                        if momentum_peak_10d is not None
                        else None
                    ),
                    exhaustion_momentum_drop_from_peak=(
                        round(momentum_drop_from_peak, 2)
                        if momentum_drop_from_peak is not None
                        else None
                    ),
                    exhaustion_leader_score_peak_5obs=(
                        round(leader_score_peak, 2) if leader_score_peak is not None else None
                    ),
                    exhaustion_leader_score_decay=(
                        round(leader_score_decay, 2) if leader_score_decay is not None else None
                    ),
                    exhaustion_rs_current=(
                        round(current_rs, 2) if current_rs is not None else None
                    ),
                    exhaustion_rs_peak_5obs=(
                        round(rs_peak, 2) if rs_peak is not None else None
                    ),
                    exhaustion_rs_decay_from_peak=(
                        round(rs_decay_from_peak, 2) if rs_decay_from_peak is not None else None
                    ),
                    exhaustion_persistence_peak_5obs=(
                        round(persistence_peak, 2) if persistence_peak is not None else None
                    ),
                    exhaustion_persistence_decay_from_peak=(
                        round(persistence_decay_from_peak, 2)
                        if persistence_decay_from_peak is not None
                        else None
                    ),
                    exhaustion_distance_ma10_decay_5d=(
                        round(distance_ma10_decay, 2)
                        if distance_ma10_decay is not None
                        else None
                    ),
                    exhaustion_distance_ma20_decay_5d=(
                        round(distance_ma20_decay, 2)
                        if distance_ma20_decay is not None
                        else None
                    ),
                )
            )
            self._remember(ticker, item, current_rs)
        return out


class ExhaustionTransitionAnalyzer:
    """Build episode-level validation tables for Exhaustion Risk V1.1."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.xcfg = cfg.get("exhaustion_risk", {})

    def events(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "exhaustion_risk_label" not in df.columns:
            return pd.DataFrame()

        work = df.copy()
        work["scan_date"] = work["scan_date"].astype(str)
        work = work.sort_values(["ticker", "scan_date"]).reset_index(drop=True)

        event_states = set(self.xcfg.get("event_states", ["LEADER", "PERSISTENT_LEADER"]))
        risk_labels = {"HIGH", "CRITICAL"}

        rows: list[dict] = []
        for _, group in work.groupby("ticker", sort=False):
            group = group.reset_index(drop=True)
            prev_event_condition = False
            for pos, row in group.iterrows():
                high_risk = str(row.get("exhaustion_risk_label", "")) in risk_labels
                eligible_state = str(row.get("lifecycle_state", "")) in event_states
                event_condition = bool(high_risk and eligible_state)
                is_event = bool(event_condition and not prev_event_condition)
                prev_event_condition = event_condition
                if not is_event:
                    continue

                rec = row.to_dict()
                rec["exhaustion_event_label"] = str(row.get("exhaustion_risk_label", ""))
                for horizon in (3, 5, 10):
                    future = group.iloc[pos + 1 : pos + 1 + horizon]
                    states = set(
                        future.get("lifecycle_state", pd.Series(dtype=str))
                        .dropna()
                        .astype(str)
                    )
                    rec[f"exhausting_within_{horizon}d"] = "EXHAUSTING" in states
                    rec[f"broken_within_{horizon}d"] = "BROKEN" in states
                rows.append(rec)
        return pd.DataFrame(rows)

    @staticmethod
    def _add_performance(row: dict[str, float | int | str], frame: pd.DataFrame) -> None:
        for col in ("D+5", "D+20", "D+60"):
            if col in frame.columns:
                values = pd.to_numeric(frame[col], errors="coerce").dropna()
                if not values.empty:
                    row[f"avg_{col}"] = round(float(values.mean()), 2)
                    row[f"median_{col}"] = round(float(values.median()), 2)
                    row[f"win_rate_{col}"] = round(float((values > 0).mean()) * 100.0, 2)

        for col in ("MFE_D20", "MAE_D20", "MFE_D60", "MAE_D60"):
            if col in frame.columns:
                values = pd.to_numeric(frame[col], errors="coerce").dropna()
                if not values.empty:
                    row[f"avg_{col}"] = round(float(values.mean()), 2)
                    row[f"median_{col}"] = round(float(values.median()), 2)

    @classmethod
    def _summary_row(cls, events: pd.DataFrame, cohort: str) -> dict[str, float | int | str]:
        row: dict[str, float | int | str] = {
            "cohort": cohort,
            "event_count": int(len(events)),
        }
        for horizon in (3, 5, 10):
            for prefix in ("exhausting", "broken"):
                col = f"{prefix}_within_{horizon}d"
                if col in events.columns:
                    row[f"{col}_rate"] = round(
                        float(events[col].fillna(False).mean()) * 100.0,
                        2,
                    )
        cls._add_performance(row, events)
        return row

    def summary(self, events: pd.DataFrame) -> pd.DataFrame:
        if events.empty:
            return pd.DataFrame()

        rows = [self._summary_row(events, "ALL")]
        if "exhaustion_event_label" in events.columns:
            for label in ("HIGH", "CRITICAL"):
                part = events[events["exhaustion_event_label"].eq(label)]
                if not part.empty:
                    rows.append(self._summary_row(part, label))
        return pd.DataFrame(rows)

    def score_report(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compare all established leaders by Exhaustion label, not only events."""
        if df.empty or "exhaustion_risk_label" not in df.columns:
            return pd.DataFrame()
        event_states = set(self.xcfg.get("event_states", ["LEADER", "PERSISTENT_LEADER"]))
        work = df[df.get("lifecycle_state", pd.Series(index=df.index, dtype=str)).isin(event_states)].copy()
        if work.empty:
            return pd.DataFrame()

        rows: list[dict[str, float | int | str]] = []
        for label in ("LOW", "WATCH", "HIGH", "CRITICAL"):
            part = work[work["exhaustion_risk_label"].eq(label)]
            if part.empty:
                continue
            row: dict[str, float | int | str] = {
                "label": label,
                "count": int(len(part)),
                "avg_exhaustion_score": round(
                    float(pd.to_numeric(part["exhaustion_risk_score"], errors="coerce").mean()),
                    2,
                ),
            }
            self._add_performance(row, part)
            rows.append(row)
        return pd.DataFrame(rows)
