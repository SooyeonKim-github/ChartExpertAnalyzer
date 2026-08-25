from __future__ import annotations

import pandas as pd
from config import FORWARD_BARS
from core.models import Candidate
from data.data_provider import PyKrxDataProvider


class EventBacktester:
    def __init__(self, provider: PyKrxDataProvider) -> None: self.provider = provider

    def enrich(self, candidates: list[Candidate]) -> pd.DataFrame:
        rows = []
        for c in candidates:
            row = c.as_record(); closes = self.provider.future_closes(c.ticker, c.date); entry = float(c.current_price)
            future = closes[closes.index > pd.Timestamp(c.date)] if len(closes) else pd.Series(dtype=float)
            for bar in FORWARD_BARS: row[f"return_d{bar}"] = float(future.iloc[bar-1]/entry-1.0) if len(future) >= bar else None
            rows.append(row)
        return pd.DataFrame(rows)


def performance_by_pattern(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty or "pattern_type" not in events: return pd.DataFrame()
    rows = []
    for pattern, group in events.groupby("pattern_type"):
        row = {"pattern_type": pattern, "events": len(group)}
        for col in [c for c in events.columns if c.startswith("return_d")]:
            vals = pd.to_numeric(group[col], errors="coerce").dropna(); row[f"avg_{col}"] = float(vals.mean()) if len(vals) else None; row[f"median_{col}"] = float(vals.median()) if len(vals) else None; row[f"win_rate_{col}"] = float((vals>0).mean()) if len(vals) else None
        rows.append(row)
    return pd.DataFrame(rows)
