from __future__ import annotations

import pandas as pd
from config import UNIVERSE
from data.data_provider import PyKrxDataProvider


class UniverseService:
    def __init__(self, provider: PyKrxDataProvider) -> None: self.provider = provider

    def build(self, as_of: str, top_n: int | None = None) -> pd.DataFrame:
        n = UNIVERSE.top_n if top_n is None else top_n; frames = []
        for market in UNIVERSE.markets:
            cap = self._find_recent_market_cap(as_of, market)
            if cap.empty: continue
            cap["market"] = market; frames.append(cap)
        if not frames: return pd.DataFrame(columns=["ticker","market_cap","market","name"])
        out = pd.concat(frames, ignore_index=True).sort_values("market_cap", ascending=False)
        if n and n > 0: out = out.head(n)
        out["name"] = [self.provider.ticker_name(t) for t in out["ticker"]]
        return out.reset_index(drop=True)

    def _find_recent_market_cap(self, as_of: str, market: str) -> pd.DataFrame:
        dt = pd.Timestamp(as_of)
        for delta in range(10):
            df = self.provider.market_cap((dt-pd.Timedelta(days=delta)).strftime("%Y%m%d"), market)
            if not df.empty: return df
        return pd.DataFrame()
