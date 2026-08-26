from __future__ import annotations

from collections import defaultdict
import numpy as np
import pandas as pd

from config import FORWARD_BARS
from core.models import Candidate
from data.data_provider import PyKrxDataProvider


class EventBacktester:
    def __init__(self, provider: PyKrxDataProvider) -> None:
        self.provider = provider

    def enrich(self, candidates: list[Candidate]) -> pd.DataFrame:
        if not candidates:
            return pd.DataFrame()
        grouped: dict[str, list[Candidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate.ticker].append(candidate)

        rows = []
        for ticker, ticker_candidates in grouped.items():
            min_date = min(pd.Timestamp(c.date) for c in ticker_candidates)
            max_date = max(pd.Timestamp(c.date) for c in ticker_candidates)
            start = min_date.strftime("%Y%m%d")
            end = (max_date + pd.Timedelta(days=150)).strftime("%Y%m%d")
            try:
                price_df = self.provider.stock_ohlcv(ticker, start, end)
            except Exception:
                price_df = pd.DataFrame()

            for c in ticker_candidates:
                row = c.as_record()
                future = price_df[price_df.index > pd.Timestamp(c.date)] if not price_df.empty else pd.DataFrame()
                if future.empty:
                    row.update({"entry_mode": "NEXT_OPEN", "entry_date": None, "entry_price": None})
                    for bar in FORWARD_BARS:
                        row[f"return_d{bar}"] = None
                        row[f"mfe_d{bar}"] = None
                        row[f"mae_d{bar}"] = None
                    rows.append(row)
                    continue

                entry_price = float(future.iloc[0]["open"])
                row["entry_mode"] = "NEXT_OPEN"
                row["entry_date"] = pd.Timestamp(future.index[0]).strftime("%Y%m%d")
                row["entry_price"] = entry_price
                for bar in FORWARD_BARS:
                    if len(future) < bar or entry_price <= 0:
                        row[f"return_d{bar}"] = None
                        row[f"mfe_d{bar}"] = None
                        row[f"mae_d{bar}"] = None
                        continue
                    window = future.iloc[:bar]
                    row[f"return_d{bar}"] = float(window.iloc[-1]["close"] / entry_price - 1.0)
                    row[f"mfe_d{bar}"] = float(window["high"].max() / entry_price - 1.0)
                    row[f"mae_d{bar}"] = float(window["low"].min() / entry_price - 1.0)
                rows.append(row)
        return pd.DataFrame(rows)


def _performance(events: pd.DataFrame, group_col: str, output_col: str | None = None) -> pd.DataFrame:
    if events.empty or group_col not in events:
        return pd.DataFrame()
    output_col = output_col or group_col
    rows = []
    for key, group in events.groupby(group_col, dropna=False):
        row = {output_col: key, "events": len(group)}
        for col in [c for c in events.columns if c.startswith("return_d")]:
            vals = pd.to_numeric(group[col], errors="coerce").dropna()
            row[f"avg_{col}"] = float(vals.mean()) if len(vals) else None
            row[f"median_{col}"] = float(vals.median()) if len(vals) else None
            row[f"win_rate_{col}"] = float((vals > 0).mean()) if len(vals) else None
        rows.append(row)
    return pd.DataFrame(rows)


def performance_by_pattern(events: pd.DataFrame) -> pd.DataFrame:
    return _performance(events, "pattern_type")


def performance_by_state(events: pd.DataFrame) -> pd.DataFrame:
    return _performance(events, "pattern_state")


def performance_by_market_regime(events: pd.DataFrame) -> pd.DataFrame:
    return _performance(events, "market_regime")


def performance_by_volume(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    d = events.copy()
    ratio = pd.to_numeric(d.get("volume_ratio"), errors="coerce")
    d["volume_bucket"] = pd.cut(ratio, bins=[-np.inf, 0.8, 1.0, 1.3, 1.6, 2.0, np.inf], right=False, labels=["<0.8", "0.8-1.0", "1.0-1.3", "1.3-1.6", "1.6-2.0", ">=2.0"])
    return _performance(d, "volume_bucket")


def performance_by_condition(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    conditions = [
        "volume_filter_pass",
        "metric_pre_breakout_volume_contraction",
        "metric_volume_oscillator_positive",
        "metric_volume_oscillator_rising",
        "metric_mfi_bullish_divergence",
        "metric_candle_bullish_momentum_candle",
        "metric_candle_bullish_pin_bar",
        "metric_candle_bullish_engulfing",
        "metric_candle_engulfing_confirmed",
        "metric_candle_inside_bar_breakout",
        "metric_candle_morning_star",
        "metric_candle_three_white_soldiers",
        "metric_candle_upper_wick_distribution_warning",
        "metric_candle_narrow_high_volume_warning",
    ]
    rows = []
    return_cols = [c for c in events.columns if c.startswith("return_d")]
    for condition in conditions:
        if condition not in events:
            continue
        mask = events[condition].fillna(False).astype(bool)
        group = events[mask]
        row = {"condition": condition, "events": len(group), "share": float(mask.mean())}
        for col in return_cols:
            vals = pd.to_numeric(group[col], errors="coerce").dropna()
            row[f"avg_{col}"] = float(vals.mean()) if len(vals) else None
            row[f"win_rate_{col}"] = float((vals > 0).mean()) if len(vals) else None
        rows.append(row)
    return pd.DataFrame(rows)
