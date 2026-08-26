from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from config import UNIVERSE
from data.data_provider import PyKrxDataProvider


class UniverseService:
    def __init__(self, provider: PyKrxDataProvider) -> None:
        self.provider = provider

    def build(self, as_of: str, top_n: int | None = None) -> pd.DataFrame:
        n = UNIVERSE.top_n if top_n is None else top_n

        # run_all_screen / run_combined_range가 만든 공통 point-in-time liquidity Universe가
        # 있으면 Bullish도 동일한 일별 TOP N membership을 그대로 사용한다.
        membership_path = os.environ.get("LIQUIDITY_MEMBERSHIP_CSV", "").strip()
        if membership_path and Path(membership_path).exists():
            out = self._from_liquidity_membership(membership_path, as_of, n)
            if not out.empty:
                return out

        frames = []
        for market in UNIVERSE.markets:
            cap = self._find_recent_market_cap(as_of, market)
            if cap.empty:
                continue
            cap["market"] = market
            frames.append(cap)
        if not frames:
            return pd.DataFrame(columns=["ticker", "market_cap", "market", "name"])
        out = pd.concat(frames, ignore_index=True).sort_values("market_cap", ascending=False)
        if n and n > 0:
            out = out.head(n)
        out["name"] = [self.provider.ticker_name(t) for t in out["ticker"]]
        return out.reset_index(drop=True)

    def _from_liquidity_membership(self, path: str, as_of: str, n: int) -> pd.DataFrame:
        try:
            df = pd.read_csv(path, encoding="utf-8-sig", dtype={"ticker": str})
        except Exception:
            return pd.DataFrame()
        if df.empty or "date" not in df.columns or "ticker" not in df.columns:
            return pd.DataFrame()
        x = df.copy()
        x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
        target = pd.Timestamp(as_of).normalize()
        day = x[x["date"].eq(target)].copy()
        if day.empty:
            available = x.loc[x["date"].le(target), "date"].dropna()
            if available.empty:
                return pd.DataFrame()
            day = x[x["date"].eq(available.max())].copy()
        if "source_rank" in day.columns:
            day = day.sort_values("source_rank")
        if n and n > 0:
            day = day.head(n)
        day["ticker"] = day["ticker"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
        if "name" not in day.columns:
            day["name"] = [self.provider.ticker_name(t) for t in day["ticker"]]
        if "market" not in day.columns:
            day["market"] = "KOSPI"
        day["market_cap"] = pd.NA
        keep = ["ticker", "market_cap", "market", "name"]
        for c in ["source_rank", "trading_value", "avg_trading_value_20d", "universe_cutoff_value"]:
            if c in day.columns:
                keep.append(c)
        return day[keep].reset_index(drop=True)

    def _find_recent_market_cap(self, as_of: str, market: str) -> pd.DataFrame:
        dt = pd.Timestamp(as_of)
        for delta in range(10):
            df = self.provider.market_cap((dt-pd.Timedelta(days=delta)).strftime("%Y%m%d"), market)
            if not df.empty:
                return df
        return pd.DataFrame()
