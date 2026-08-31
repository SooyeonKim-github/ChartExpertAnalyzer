from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


STAGE2_SIGNALS = {"BOX_RETEST_CONFIRMED"}
STAGE3_SIGNALS = {"BOX_BREAKOUT", "PRIOR_HIGH_BREAKOUT", "PULLBACK_STRONG_CONFIRMATION"}


@dataclass(frozen=True)
class ScaleInPlan:
    stage1_weight: float = 0.34
    stage2_weight: float = 0.33
    stage3_weight: float = 0.33

    def weight(self, stage: int) -> float:
        if stage == 1:
            return self.stage1_weight
        if stage == 2:
            return self.stage2_weight
        if stage == 3:
            return self.stage3_weight
        raise ValueError(f"지원하지 않는 진입 단계: {stage}")


def empty_trade_fields() -> dict:
    return {
        "Trade_Entry_Date": "",
        "Trade_Entry_Price": np.nan,
        "Trade_Exit_Date": "",
        "Trade_Exit_Price": np.nan,
        "Trade_Exit_Reason": "",
        "Trade_Holding_Bars": np.nan,
        "Trade_Return_Pct": np.nan,
        "Portfolio_Return_Pct": np.nan,
        "Trade_MFE_Pct": np.nan,
        "Trade_MAE_Pct": np.nan,
        "Trade_Complete": 0,
    }


def empty_position_fields() -> dict:
    return {
        "Position_ID": "",
        "Position_Action": "",
        "Entry_Stage": 0,
        "Entry_Allocation_Pct": 0.0,
        "Entry_Fill_Date": "",
        "Entry_Fill_Price": np.nan,
    }


def _planned_stage(position: dict | None, signal: str) -> int:
    if position is None:
        return 1
    filled = len(position["entries"])
    if filled == 1 and signal in STAGE2_SIGNALS:
        return 2
    if filled == 2 and signal in STAGE3_SIGNALS:
        return 3
    return 0


def _portfolio_value(entries: list[dict], price: float) -> float:
    invested = sum(float(e["weight"]) for e in entries)
    shares = sum(float(e["weight"]) / float(e["price"]) for e in entries)
    return (1.0 - invested) + shares * float(price)


def _avg_entry_price(entries: list[dict]) -> float:
    invested = sum(float(e["weight"]) for e in entries)
    shares = sum(float(e["weight"]) / float(e["price"]) for e in entries)
    return invested / shares if shares > 0 else float("nan")


def _finalize_trade(full: pd.DataFrame, position: dict, exit_pos: int, exit_price: float, exit_reason: str) -> dict:
    entries = position["entries"]
    first_entry_pos = int(entries[0]["entry_pos"])
    invested_weight = sum(float(e["weight"]) for e in entries)
    shares = sum(float(e["weight"]) / float(e["price"]) for e in entries)
    invested_value_at_exit = shares * float(exit_price)
    invested_return = (invested_value_at_exit / invested_weight - 1.0) * 100.0 if invested_weight > 0 else np.nan
    portfolio_return = (_portfolio_value(entries, float(exit_price)) - 1.0) * 100.0

    max_value = -np.inf
    min_value = np.inf
    for i in range(first_entry_pos, exit_pos + 1):
        active = [e for e in entries if int(e["entry_pos"]) <= i]
        if not active:
            continue
        high_value = _portfolio_value(active, float(full["High"].iloc[i]))
        low_value = _portfolio_value(active, float(full["Low"].iloc[i]))
        max_value = max(max_value, high_value)
        min_value = min(min_value, low_value)

    row = {
        "Position_ID": position["position_id"],
        "Ticker": position["ticker"],
        "Name": position["name"],
        "Market": position["market"],
        "Stage1_Signal_Date": position["stage1_signal_date"],
        "Stage1_Status": position["stage1_status"],
        "Stage1_Primary_Signal": position["stage1_signal"],
        "Filled_Stages": len(entries),
        "Invested_Weight_Pct": invested_weight * 100.0,
        "Avg_Entry_Price": _avg_entry_price(entries),
        "Trade_Entry_Date": full.index[first_entry_pos].strftime("%Y-%m-%d"),
        "Trade_Entry_Price": _avg_entry_price(entries),
        "Trade_Exit_Date": full.index[exit_pos].strftime("%Y-%m-%d"),
        "Trade_Exit_Price": float(exit_price),
        "Trade_Exit_Reason": exit_reason,
        "Trade_Holding_Bars": int(exit_pos - first_entry_pos + 1),
        "Trade_Return_Pct": invested_return,
        "Portfolio_Return_Pct": portfolio_return,
        "Trade_MFE_Pct": (max_value - 1.0) * 100.0 if np.isfinite(max_value) else np.nan,
        "Trade_MAE_Pct": (min_value - 1.0) * 100.0 if np.isfinite(min_value) else np.nan,
        "Trade_Complete": int(exit_reason != "DATA_END"),
        "Final_Stop_Price": float(position["stop"]),
    }
    for stage in (1, 2, 3):
        e = next((x for x in entries if int(x["stage"]) == stage), None)
        row[f"Stage{stage}_Signal_Date"] = e["signal_date"] if e else ""
        row[f"Stage{stage}_Entry_Date"] = e["entry_date"] if e else ""
        row[f"Stage{stage}_Entry_Price"] = float(e["price"]) if e else np.nan
        row[f"Stage{stage}_Allocation_Pct"] = float(e["weight"]) * 100.0 if e else 0.0
        row[f"Stage{stage}_Primary_Signal"] = e["signal"] if e else ""
        row[f"Stage{stage}_Return_Pct"] = (
            (float(exit_price) / float(e["price"]) - 1.0) * 100.0 if e else np.nan
        )
    return row


def simulate_scaled_positions(
    full: pd.DataFrame,
    signal_events: list[dict],
    ticker: str,
    name: str,
    market: str,
    short_ma_period: int,
    max_bars: int,
    plan: ScaleInPlan,
) -> tuple[dict[int, dict], list[dict], list[dict]]:
    """Confirmed signals -> one stateful position with up to three staged entries.

    Stage 1: first confirmed signal while flat.
    Stage 2: BOX_RETEST_CONFIRMED while holding one stage.
    Stage 3: later BOX/PRIOR_HIGH/strong-pullback confirmation while holding two stages.

    Every fill is executed at the next trading day's open. Same-stage repeated signals
    are ignored instead of being suppressed by a time cooldown.
    """
    if not signal_events:
        return {}, [], []

    events_by_pos = {int(e["pos"]): e for e in signal_events}
    ma_short = full["Close"].rolling(short_ma_period).mean()
    annotations: dict[int, dict] = {}
    trade_rows: list[dict] = []
    entry_rows: list[dict] = []

    position: dict | None = None
    pending: dict | None = None
    position_seq = 0
    first_signal_pos = min(events_by_pos)

    for i in range(first_signal_pos, len(full)):
        open_ = float(full["Open"].iloc[i])
        low = float(full["Low"].iloc[i])
        close = float(full["Close"].iloc[i])

        if position is not None and open_ < float(position["stop"]):
            trade = _finalize_trade(full, position, i, open_, "POSITION_STOP_GAP")
            trade_rows.append(trade)
            stage1_row = int(position["stage1_row_idx"])
            annotations.setdefault(stage1_row, {}).update({
                k: trade[k] for k in empty_trade_fields().keys()
            })
            position = None
            pending = None

        if pending is not None and int(pending["entry_pos"]) == i:
            stage = int(pending["stage"])
            weight = plan.weight(stage)
            if position is None and stage != 1:
                annotations.setdefault(int(pending["row_idx"]), {}).update({
                    "Position_Action": "ADD_CANCELLED_NO_POSITION",
                    "Entry_Stage": stage,
                })
                pending = None
            else:
                if stage == 1:
                    position_seq += 1
                    position_id = f"{ticker}-{position_seq:03d}"
                    position = {
                        "position_id": position_id,
                        "ticker": ticker,
                        "name": name,
                        "market": market,
                        "entries": [],
                        "stop": float(pending["signal_low"]),
                        "stage1_signal_date": pending["signal_date"],
                        "stage1_status": pending["status"],
                        "stage1_signal": pending["signal"],
                        "stage1_row_idx": int(pending["row_idx"]),
                        "max_exit_pos": min(len(full) - 1, i + max_bars - 1),
                    }
                entry = {
                    "stage": stage,
                    "weight": weight,
                    "price": open_,
                    "entry_pos": i,
                    "entry_date": full.index[i].strftime("%Y-%m-%d"),
                    "signal_date": pending["signal_date"],
                    "signal": pending["signal"],
                    "status": pending["status"],
                    "signal_low": float(pending["signal_low"]),
                    "row_idx": int(pending["row_idx"]),
                }
                position["entries"].append(entry)
                position["stop"] = max(float(position["stop"]), float(pending["signal_low"]))
                action = f"STAGE{stage}_ENTRY"
                ann = {
                    "Position_ID": position["position_id"],
                    "Position_Action": action,
                    "Entry_Stage": stage,
                    "Entry_Allocation_Pct": weight * 100.0,
                    "Entry_Fill_Date": entry["entry_date"],
                    "Entry_Fill_Price": open_,
                }
                annotations.setdefault(int(pending["row_idx"]), {}).update(ann)
                entry_rows.append({
                    "Position_ID": position["position_id"],
                    "Ticker": ticker,
                    "Name": name,
                    "Market": market,
                    "Stage": stage,
                    "Allocation_Pct": weight * 100.0,
                    "Signal_Date": pending["signal_date"],
                    "Entry_Date": entry["entry_date"],
                    "Entry_Price": open_,
                    "Status": pending["status"],
                    "Primary_Signal": pending["signal"],
                    "Signal_Low": float(pending["signal_low"]),
                    "Position_Stop_After_Entry": float(position["stop"]),
                })
                pending = None

        if position is not None:
            if low <= float(position["stop"]):
                trade = _finalize_trade(full, position, i, float(position["stop"]), "POSITION_STOP")
                trade_rows.append(trade)
                stage1_row = int(position["stage1_row_idx"])
                annotations.setdefault(stage1_row, {}).update({k: trade[k] for k in empty_trade_fields().keys()})
                position = None
                pending = None
            elif pd.notna(ma_short.iloc[i]) and close < float(ma_short.iloc[i]):
                trade = _finalize_trade(full, position, i, close, "SHORT_MA_CLOSE")
                trade_rows.append(trade)
                stage1_row = int(position["stage1_row_idx"])
                annotations.setdefault(stage1_row, {}).update({k: trade[k] for k in empty_trade_fields().keys()})
                position = None
                pending = None
            elif i >= int(position["max_exit_pos"]):
                reason = "TIME_EXIT" if i < len(full) - 1 else "DATA_END"
                trade = _finalize_trade(full, position, i, close, reason)
                trade_rows.append(trade)
                stage1_row = int(position["stage1_row_idx"])
                annotations.setdefault(stage1_row, {}).update({k: trade[k] for k in empty_trade_fields().keys()})
                position = None
                pending = None

        event = events_by_pos.get(i)
        if event is not None:
            row_idx = int(event["row_idx"])
            annotations.setdefault(row_idx, {}).update(empty_position_fields())
            if pending is not None:
                annotations[row_idx]["Position_Action"] = "IGNORED_PENDING_ORDER"
                continue
            stage = _planned_stage(position, str(event["signal"]))
            if stage == 0:
                annotations[row_idx]["Position_ID"] = position["position_id"] if position is not None else ""
                annotations[row_idx]["Position_Action"] = "IGNORED_REPEAT_OR_STAGE_NOT_READY"
                continue
            if i + 1 >= len(full):
                annotations[row_idx]["Position_ID"] = position["position_id"] if position is not None else ""
                annotations[row_idx]["Position_Action"] = "ENTRY_SKIPPED_NO_NEXT_BAR"
                annotations[row_idx]["Entry_Stage"] = stage
                continue
            pending = {
                "stage": stage,
                "entry_pos": i + 1,
                "row_idx": row_idx,
                "signal_date": event["signal_date"],
                "status": event["status"],
                "signal": event["signal"],
                "signal_low": float(event["signal_low"]),
            }
            annotations[row_idx].update({
                "Position_ID": position["position_id"] if position is not None else f"{ticker}-{position_seq + 1:03d}",
                "Position_Action": f"STAGE{stage}_SCHEDULED",
                "Entry_Stage": stage,
                "Entry_Allocation_Pct": plan.weight(stage) * 100.0,
            })

    if position is not None:
        i = len(full) - 1
        trade = _finalize_trade(full, position, i, float(full["Close"].iloc[i]), "DATA_END")
        trade_rows.append(trade)
        stage1_row = int(position["stage1_row_idx"])
        annotations.setdefault(stage1_row, {}).update({k: trade[k] for k in empty_trade_fields().keys()})

    return annotations, trade_rows, entry_rows
