from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .leadership_history import LeadershipHistoryContext
from .models import LeaderResult


class ExhaustionRiskEngine:
    """Score early leadership exhaustion without changing confirmation rules.

    Score composition (0~100):
      - Overextension / heat          25
      - Momentum deceleration         25
      - Distribution / breakout fail 20
      - Money-flow / rank decay       15
      - Price-structure damage        15

    V1 is observational. The score is exported for backtesting but does not
    directly change lifecycle state, Leader Score, Timing Score, or status.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.xcfg = cfg.get("exhaustion_risk", {})

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

    @staticmethod
    def _atr14(df: pd.DataFrame) -> float | None:
        if df is None or df.empty or len(df) < 2:
            return None
        high = pd.to_numeric(df.get("high"), errors="coerce")
        low = pd.to_numeric(df.get("low"), errors="coerce")
        close = pd.to_numeric(df.get("close"), errors="coerce")
        if high is None or low is None or close is None:
            return None
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
    def _score_overextension(
        *,
        distance_ma20_pct: float | None,
        return_5d: float | None,
        atr_extension: float | None,
        chase_risk: float,
    ) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        d20 = float(distance_ma20_pct or 0.0)
        r5 = float(return_5d or 0.0)
        atrx = float(atr_extension or 0.0)

        if d20 >= 20:
            score += 10
            flags.append("ma20_extreme_extension")
        elif d20 >= 15:
            score += 8
            flags.append("ma20_high_extension")
        elif d20 >= 10:
            score += 5
        elif d20 >= 6:
            score += 2

        if r5 >= 25:
            score += 6
            flags.append("five_day_parabolic")
        elif r5 >= 15:
            score += 4
        elif r5 >= 10:
            score += 2

        if atrx >= 3.0:
            score += 5
            flags.append("atr_extreme_extension")
        elif atrx >= 2.0:
            score += 3
        elif atrx >= 1.5:
            score += 1

        if chase_risk >= 70:
            score += 4
            flags.append("high_chase_risk")
        elif chase_risk >= 50:
            score += 2

        return min(25.0, score), flags

    @staticmethod
    def _score_deceleration(
        *,
        price_momentum_deceleration: float | None,
        rs_deceleration: float | None,
        rank_acceleration: float | None,
        return_1d: float,
        return_5d: float | None,
    ) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        pdec = float(price_momentum_deceleration or 0.0)
        rsdec = float(rs_deceleration or 0.0)
        racc = float(rank_acceleration or 0.0)

        if pdec >= 12:
            score += 10
            flags.append("price_momentum_sharp_deceleration")
        elif pdec >= 7:
            score += 7
        elif pdec >= 3:
            score += 4

        if rsdec >= 8:
            score += 7
            flags.append("rs_sharp_deceleration")
        elif rsdec >= 4:
            score += 5
        elif rsdec >= 2:
            score += 3

        if racc <= -10:
            score += 5
            flags.append("rank_velocity_reversal")
        elif racc <= -5:
            score += 3
        elif racc < 0:
            score += 1

        if return_1d < 0 and float(return_5d or 0.0) >= 10:
            score += 3
            flags.append("negative_day_after_fast_run")

        return min(25.0, score), flags

    @staticmethod
    def _score_distribution(item: LeaderResult) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []

        if item.false_breakout_flag:
            score += 10
            flags.append("false_breakout")
        if item.breakout_exhaustion_risk:
            score += 8
            flags.append("breakout_exhaustion")

        wick = float(item.upper_wick_ratio or 0.0)
        if wick >= 0.55:
            score += 6
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
            score += 4
            flags.append("high_volume_down_day")

        return min(20.0, score), flags

    @staticmethod
    def _score_money_flow(
        *,
        rank_reversal_3d: float | None,
        rank_reversal_5d: float | None,
        trading_value_decay_ratio: float | None,
        persistence_score: float | None,
        persistence_available: bool,
    ) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        r3 = float(rank_reversal_3d or 0.0)
        r5 = float(rank_reversal_5d or 0.0)

        if r3 >= 20:
            score += 5
            flags.append("rank_reversal_3d")
        elif r3 >= 10:
            score += 3
        elif r3 >= 5:
            score += 1

        if r5 >= 30:
            score += 4
            flags.append("rank_reversal_5d")
        elif r5 >= 15:
            score += 2

        if trading_value_decay_ratio is not None:
            decay = float(trading_value_decay_ratio)
            if decay <= 0.35:
                score += 4
                flags.append("trading_value_sharp_decay")
            elif decay <= 0.50:
                score += 3
            elif decay <= 0.70:
                score += 1

        if persistence_available and persistence_score is not None:
            p = float(persistence_score)
            if p < 45:
                score += 2
                flags.append("persistence_decay")
            elif p < 60:
                score += 1

        return min(15.0, score), flags

    @staticmethod
    def _score_structure(
        *,
        drawdown_20d_pct: float | None,
        below_ma10: bool,
        below_ma20: bool,
        ma20_slope_5d_pct: float | None,
    ) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        dd = float(drawdown_20d_pct or 0.0)

        if dd <= -12:
            score += 6
            flags.append("deep_20d_drawdown")
        elif dd <= -8:
            score += 4
        elif dd <= -5:
            score += 2

        if below_ma10:
            score += 3
            flags.append("below_ma10")
        if below_ma20:
            score += 5
            flags.append("below_ma20")

        slope = float(ma20_slope_5d_pct or 0.0)
        if slope <= -2:
            score += 3
            flags.append("ma20_slope_down")
        elif slope < 0:
            score += 1

        return min(15.0, score), flags

    def enrich(
        self,
        results: list[LeaderResult],
        *,
        daily_by_ticker: dict[str, pd.DataFrame],
        history: LeadershipHistoryContext,
    ) -> list[LeaderResult]:
        if not results or not self.xcfg.get("enabled", True):
            return results

        watch_score = float(self.xcfg.get("watch_score", 35.0))
        high_score = float(self.xcfg.get("high_score", 55.0))
        critical_score = float(self.xcfg.get("critical_score", 75.0))

        out: list[LeaderResult] = []
        for item in results:
            ticker = str(item.ticker).zfill(6)
            daily = daily_by_ticker.get(ticker, pd.DataFrame())
            close = self._series(daily, "close")
            if close.empty:
                out.append(item)
                continue

            current = float(close.iloc[-1])
            ma10 = float(close.tail(10).mean()) if len(close) >= 10 else None
            ma20 = float(close.tail(20).mean()) if len(close) >= 20 else None
            distance_ma10 = ((current / ma10) - 1.0) * 100.0 if ma10 and ma10 > 0 else None
            distance_ma20 = ((current / ma20) - 1.0) * 100.0 if ma20 and ma20 > 0 else None

            high20 = float(close.tail(20).max()) if len(close) >= 1 else current
            drawdown20 = ((current / high20) - 1.0) * 100.0 if high20 > 0 else None

            return_5d = self._period_return(close, 5)
            return_10d = self._period_return(close, 10)
            latest_3d = self._period_return(close, 3)
            previous_3d = self._period_return(close, 3, offset=3)
            price_deceleration = (
                float(previous_3d) - float(latest_3d)
                if latest_3d is not None and previous_3d is not None
                else None
            )

            rs_deceleration = (
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

            ma20_slope = None
            if len(close) >= 25:
                ma20_now = float(close.tail(20).mean())
                ma20_prev = float(close.iloc[:-5].tail(20).mean())
                if ma20_prev > 0:
                    ma20_slope = (ma20_now / ma20_prev - 1.0) * 100.0

            ranks = history.ranks(ticker) if history.available else pd.Series(dtype=float)
            values = history.trading_values(ticker) if history.available else pd.Series(dtype=float)
            rank_today = float(ranks.iloc[-1]) if not ranks.empty else float(item.trading_value_rank)
            prior3 = pd.to_numeric(ranks.iloc[:-1].tail(3), errors="coerce").dropna()
            prior5 = pd.to_numeric(ranks.iloc[:-1].tail(5), errors="coerce").dropna()
            rank_reversal_3d = (
                rank_today - float(prior3.min()) if not prior3.empty else None
            )
            rank_reversal_5d = (
                rank_today - float(prior5.min()) if not prior5.empty else None
            )

            tv_decay_ratio = None
            if not values.empty:
                today_value = float(values.iloc[-1])
                prior_values = pd.to_numeric(values.iloc[:-1].tail(5), errors="coerce").dropna()
                if not prior_values.empty and float(prior_values.max()) > 0:
                    tv_decay_ratio = today_value / float(prior_values.max())

            over_score, over_flags = self._score_overextension(
                distance_ma20_pct=distance_ma20,
                return_5d=return_5d,
                atr_extension=atr_extension,
                chase_risk=float(item.chase_risk or 0.0),
            )
            decel_score, decel_flags = self._score_deceleration(
                price_momentum_deceleration=price_deceleration,
                rs_deceleration=rs_deceleration,
                rank_acceleration=item.rank_acceleration,
                return_1d=float(item.return_pct or 0.0),
                return_5d=return_5d,
            )
            distribution_score, distribution_flags = self._score_distribution(item)
            money_score, money_flags = self._score_money_flow(
                rank_reversal_3d=rank_reversal_3d,
                rank_reversal_5d=rank_reversal_5d,
                trading_value_decay_ratio=tv_decay_ratio,
                persistence_score=item.leader_persistence_score,
                persistence_available=item.persistence_available,
            )
            structure_score, structure_flags = self._score_structure(
                drawdown_20d_pct=drawdown20,
                below_ma10=bool(ma10 is not None and current < ma10),
                below_ma20=bool(ma20 is not None and current < ma20),
                ma20_slope_5d_pct=ma20_slope,
            )

            total_score = round(
                over_score
                + decel_score
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

            flags = list(dict.fromkeys(
                over_flags
                + decel_flags
                + distribution_flags
                + money_flags
                + structure_flags
            ))

            out.append(
                replace(
                    item,
                    exhaustion_risk_available=True,
                    exhaustion_risk_score=total_score,
                    exhaustion_risk_label=label,
                    exhaustion_overextension_score=round(over_score, 2),
                    exhaustion_deceleration_score=round(decel_score, 2),
                    exhaustion_distribution_score=round(distribution_score, 2),
                    exhaustion_money_flow_decay_score=round(money_score, 2),
                    exhaustion_structure_score=round(structure_score, 2),
                    exhaustion_flags=",".join(flags),
                    exhaustion_return_5d=round(return_5d, 2) if return_5d is not None else None,
                    exhaustion_return_10d=round(return_10d, 2) if return_10d is not None else None,
                    price_momentum_deceleration=(
                        round(price_deceleration, 2)
                        if price_deceleration is not None
                        else None
                    ),
                    rs_deceleration=round(rs_deceleration, 2) if rs_deceleration is not None else None,
                    rank_reversal_3d=round(rank_reversal_3d, 2) if rank_reversal_3d is not None else None,
                    rank_reversal_5d=round(rank_reversal_5d, 2) if rank_reversal_5d is not None else None,
                    trading_value_decay_ratio=(
                        round(tv_decay_ratio, 3) if tv_decay_ratio is not None else None
                    ),
                    exhaustion_distance_ma10_pct=(
                        round(distance_ma10, 2) if distance_ma10 is not None else None
                    ),
                    exhaustion_distance_ma20_pct=(
                        round(distance_ma20, 2) if distance_ma20 is not None else None
                    ),
                    atr_extension=round(atr_extension, 2) if atr_extension is not None else None,
                    exhaustion_ma20_slope_5d_pct=(
                        round(ma20_slope, 2) if ma20_slope is not None else None
                    ),
                    exhaustion_drawdown_20d_pct=(
                        round(drawdown20, 2) if drawdown20 is not None else None
                    ),
                    exhaustion_below_ma10=bool(ma10 is not None and current < ma10),
                    exhaustion_below_ma20=bool(ma20 is not None and current < ma20),
                )
            )
        return out


class ExhaustionTransitionAnalyzer:
    """Build episode-level validation tables for Exhaustion Risk V1."""

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
            prev_high_risk = False
            for pos, row in group.iterrows():
                high_risk = str(row.get("exhaustion_risk_label", "")) in risk_labels
                eligible_state = str(row.get("lifecycle_state", "")) in event_states
                is_event = bool(high_risk and eligible_state and not prev_high_risk)
                prev_high_risk = high_risk
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
    def _summary_row(events: pd.DataFrame, cohort: str) -> dict[str, float | int | str]:
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

        for col in ("D+5", "D+20", "D+60"):
            if col in events.columns:
                values = pd.to_numeric(events[col], errors="coerce").dropna()
                if not values.empty:
                    row[f"avg_{col}"] = round(float(values.mean()), 2)
                    row[f"median_{col}"] = round(float(values.median()), 2)
                    row[f"win_rate_{col}"] = round(float((values > 0).mean()) * 100.0, 2)

        for col in ("MFE_D20", "MAE_D20", "MFE_D60", "MAE_D60"):
            if col in events.columns:
                values = pd.to_numeric(events[col], errors="coerce").dropna()
                if not values.empty:
                    row[f"avg_{col}"] = round(float(values.mean()), 2)
                    row[f"median_{col}"] = round(float(values.median()), 2)
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
