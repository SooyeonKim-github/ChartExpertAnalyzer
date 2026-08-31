from __future__ import annotations

import math

import pandas as pd

from .config import StrategyConfig
from .indicators import add_indicators
from .position_manager import PositionState, build_entry_plan
from .signals import add_signals


class DynamicChartAnalyzer:
    """Stateful 3-stage chart analyzer.

    The analyzer only allows Stage 1 -> Stage 2 -> Stage 3 in chronological order.
    Staged trend exits (10/20/70) are activated after Stage 3 confirmation. Earlier
    partial positions are protected by a swing stop and signal-age timeouts.
    """

    def __init__(self, config: StrategyConfig | None = None, include_dynamic_rsi: bool = False):
        self.config = config or StrategyConfig()
        self.config.validate()
        self.include_dynamic_rsi = include_dynamic_rsi

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out.columns = [str(c).strip().lower() for c in out.columns]
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(out.columns)
        if missing:
            raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"])
            out = out.set_index("date")
        out = out.sort_index()
        for c in required:
            out[c] = pd.to_numeric(out[c], errors="coerce")
        return out.dropna(subset=list(required))

    @staticmethod
    def _finite_or_none(value) -> float | None:
        try:
            x = float(value)
            return x if math.isfinite(x) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _stop_fill_price(side: str, row: pd.Series, stop_price: float) -> float:
        """Conservative daily-bar stop fill with gap handling."""
        open_price = float(row["open"])
        if side == "LONG":
            return min(stop_price, open_price) if open_price < stop_price else stop_price
        return max(stop_price, open_price) if open_price > stop_price else stop_price

    @staticmethod
    def _status(state: PositionState) -> str:
        if state.side is None:
            return "FLAT"
        return {
            1: f"{state.side}_EARLY",
            2: f"{state.side}_CONFIRMING",
            3: f"{state.side}_CONFIRMED",
        }.get(state.stage, f"{state.side}_UNKNOWN")

    def analyze(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        data = self._normalize(df)
        data = add_indicators(data, self.config, self.include_dynamic_rsi)
        data = add_signals(data, self.config)

        state = PositionState()
        stage1_bar: int | None = None
        stage2_bar: int | None = None

        # State/reporting columns are intentionally produced by the state machine,
        # not inferred later from independent signal columns.
        for col, default in {
            "position_status": "FLAT",
            "position_stage": 0,
            "position_side": "",
            "position_market_value_krw": 0.0,
            "position_invested_krw": 0.0,
            "position_unrealized_pnl_krw": 0.0,
            "position_stop_price": float("nan"),
            "reference_target_price": float("nan"),
            "planned_next_entry_krw": 0.0,
            "bar_actions": "",
        }.items():
            data[col] = default

        for bar_idx, (dt, row) in enumerate(data.iterrows()):
            price = float(row["close"])
            events_before = len(state.events)

            # 1) Flat -> only Stage 1 can open a new trade.
            opened_this_bar = False
            entered_stage3_this_bar = False
            if state.side is None:
                if bool(row.get("long_stage1", False)):
                    stop = self._finite_or_none(row.get("long_stop_reference"))
                    if stop is not None and stop >= price:
                        stop = None
                    plan = build_entry_plan(self.config, price, stop)
                    state.enter_stage(
                        "LONG",
                        1,
                        dt,
                        price,
                        plan,
                        stop_price=stop,
                        reference_rr=self.config.long_reference_rr,
                    )
                    stage1_bar, stage2_bar = bar_idx, None
                    opened_this_bar = True
                elif bool(row.get("short_stage1", False)):
                    stop = self._finite_or_none(row.get("short_stop_reference"))
                    if stop is not None and stop <= price:
                        stop = None
                    plan = build_entry_plan(self.config, price, stop)
                    state.enter_stage(
                        "SHORT",
                        1,
                        dt,
                        price,
                        plan,
                        stop_price=stop,
                        reference_rr=self.config.short_reference_rr,
                    )
                    stage1_bar, stage2_bar = bar_idx, None
                    opened_this_bar = True

            # 2) Existing position: protective stop first. A close-based Stage-1 entry
            #    cannot be stopped by the low/high that occurred earlier on the same bar.
            if (
                not opened_this_bar
                and state.side is not None
                and self.config.use_protective_stop
                and state.stop_price is not None
            ):
                stop_hit = (
                    (state.side == "LONG" and float(row["low"]) <= state.stop_price)
                    or (state.side == "SHORT" and float(row["high"]) >= state.stop_price)
                )
                if stop_hit:
                    fill = self._stop_fill_price(state.side, row, state.stop_price)
                    state.exit_all(dt, fill, "PROTECTIVE_SWING_STOP")
                    stage1_bar, stage2_bar = None, None

            # 3) Pre-confirmation signal expiry. This is an implementation safeguard:
            #    the lecture's three confirmations are intended as one developing setup,
            #    not unrelated signals separated by an arbitrary number of months.
            if not opened_this_bar and state.side is not None and state.stage == 1 and stage1_bar is not None:
                if bar_idx - stage1_bar > self.config.stage2_max_wait_bars:
                    state.exit_all(dt, price, "STAGE2_CONFIRMATION_TIMEOUT")
                    stage1_bar, stage2_bar = None, None
            elif not opened_this_bar and state.side is not None and state.stage == 2 and stage2_bar is not None:
                if bar_idx - stage2_bar > self.config.stage3_max_wait_bars:
                    state.exit_all(dt, price, "STAGE3_CONFIRMATION_TIMEOUT")
                    stage1_bar, stage2_bar = None, None

            # 4) Sequential confirmation entries.
            if not opened_this_bar and state.side == "LONG":
                if state.stage == 1 and bool(row.get("long_stage2", False)):
                    state.enter_stage("LONG", 2, dt, price, state.entry_plan)
                    stage2_bar = bar_idx
                elif state.stage == 2 and bool(row.get("long_stage3", False)):
                    state.enter_stage("LONG", 3, dt, price, state.entry_plan)
                    entered_stage3_this_bar = True

                # The 10/20/70 trend-following exit sequence only applies after the
                # strategy has reached full Stage-3 confirmation.
                if state.side == "LONG" and state.stage == 3 and not entered_stage3_this_bar:
                    if bool(row.get("long_exit1", False)):
                        state.exit_part(1, dt, price, "MACD_DEAD_CROSS")
                    if state.side == "LONG" and bool(row.get("long_exit2", False)):
                        state.exit_part(2, dt, price, "RSI_BELOW_50")
                    if state.side == "LONG" and bool(row.get("long_exit3", False)):
                        state.exit_part(3, dt, price, "CLOUD_BREAKDOWN")
                        if state.side is None:
                            stage1_bar, stage2_bar = None, None

            elif not opened_this_bar and state.side == "SHORT":
                if state.stage == 1 and bool(row.get("short_stage2", False)):
                    state.enter_stage("SHORT", 2, dt, price, state.entry_plan)
                    stage2_bar = bar_idx
                elif state.stage == 2 and bool(row.get("short_stage3", False)):
                    state.enter_stage("SHORT", 3, dt, price, state.entry_plan)
                    entered_stage3_this_bar = True

                if state.side == "SHORT" and state.stage == 3 and not entered_stage3_this_bar:
                    if bool(row.get("short_exit1", False)):
                        state.exit_part(1, dt, price, "MACD_GOLDEN_CROSS")
                    if state.side == "SHORT" and bool(row.get("short_exit2", False)):
                        state.exit_part(2, dt, price, "RSI_ABOVE_50")
                    if state.side == "SHORT" and bool(row.get("short_exit3", False)):
                        state.exit_part(3, dt, price, "CLOUD_BREAKOUT")
                        if state.side is None:
                            stage1_bar, stage2_bar = None, None

            # 5) Persist state for CSV/manual review.
            data.at[dt, "position_status"] = self._status(state)
            data.at[dt, "position_stage"] = state.stage
            data.at[dt, "position_side"] = state.side or ""
            data.at[dt, "position_market_value_krw"] = state.total_quantity * price
            data.at[dt, "position_invested_krw"] = state.invested_amount
            data.at[dt, "position_unrealized_pnl_krw"] = state.unrealized_pnl(price)
            data.at[dt, "position_stop_price"] = state.stop_price if state.stop_price is not None else float("nan")
            data.at[dt, "reference_target_price"] = (
                state.reference_target_price if state.reference_target_price is not None else float("nan")
            )
            if state.entry_plan is not None and state.stage < 3:
                next_amount = {
                    0: state.entry_plan.stage1_amount,
                    1: state.entry_plan.stage2_amount,
                    2: state.entry_plan.stage3_amount,
                }.get(state.stage, 0.0)
            else:
                next_amount = 0.0
            data.at[dt, "planned_next_entry_krw"] = next_amount

            new_events = state.events[events_before:]
            data.at[dt, "bar_actions"] = " | ".join(e["action"] for e in new_events)

        events = pd.DataFrame(state.events)
        return data, events

    def latest_summary(self, analyzed: pd.DataFrame) -> dict:
        if analyzed.empty:
            return {}
        row = analyzed.iloc[-1]
        return {
            "date": analyzed.index[-1],
            "close": float(row["close"]),
            "rsi": None if pd.isna(row["rsi"]) else float(row["rsi"]),
            "macd": None if pd.isna(row["macd"]) else float(row["macd"]),
            "macd_signal": None if pd.isna(row["macd_signal"]) else float(row["macd_signal"]),
            "position_status": row.get("position_status", "FLAT"),
            "position_stage": int(row.get("position_stage", 0)),
            "position_invested_krw": float(row.get("position_invested_krw", 0.0)),
            "planned_next_entry_krw": float(row.get("planned_next_entry_krw", 0.0)),
            "stop_price": None if pd.isna(row.get("position_stop_price")) else float(row["position_stop_price"]),
            "bullish_divergence_recent": bool(row.get("bullish_divergence_recent", False)),
            "above_cloud": bool(row.get("above_cloud", False)),
            "long_stage1": bool(row.get("long_stage1", False)),
            "long_stage2": bool(row.get("long_stage2", False)),
            "long_stage3": bool(row.get("long_stage3", False)),
            "short_stage1": bool(row.get("short_stage1", False)),
            "short_stage2": bool(row.get("short_stage2", False)),
            "short_stage3": bool(row.get("short_stage3", False)),
        }
