from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class USStockInfo:
    ticker: str
    name: str
    market: str = "US"
    market_cap: float | None = None
    trading_value: float | None = None
    volume: float | None = None
    source_rank: int | None = None
    exchange: str = ""


def _num(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(result) else result


class USUniverseService:
    """Read the shared current US market-cap universe generated at repo root."""

    def __init__(self, universe_path: str | Path) -> None:
        self.universe_path = Path(universe_path)
        # KJB range's optional sector service probes this attribute. US range
        # disables the KR sector service, but retaining it keeps the interface.
        self.info_excel_path = self.universe_path
        self._cache: pd.DataFrame | None = None

    def load_universe_df(self) -> pd.DataFrame:
        if self._cache is not None:
            return self._cache.copy()
        if not self.universe_path.exists():
            raise FileNotFoundError(f"US universe CSV not found: {self.universe_path}")

        df = pd.read_csv(self.universe_path, encoding="utf-8-sig", dtype={"ticker": str})
        required = {"ticker", "name", "market_cap"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"US universe required columns missing: {sorted(missing)}")

        out = df.copy()
        out["ticker"] = out["ticker"].fillna("").astype(str).str.strip().str.upper()
        out["name"] = out["name"].fillna("").astype(str).str.strip()
        out["market"] = out.get("market", "US")
        if not isinstance(out["market"], pd.Series):
            out["market"] = "US"
        out["market"] = out["market"].fillna("US").astype(str).str.upper()
        for col in ["market_cap", "trading_value", "volume", "source_rank"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        if "exchange" not in out.columns:
            out["exchange"] = ""
        out = out[out["ticker"].ne("")].drop_duplicates("ticker", keep="first")
        out = out.sort_values(["market_cap", "ticker"], ascending=[False, True], na_position="last")
        self._cache = out.reset_index(drop=True)
        return self._cache.copy()

    def get_universe(
        self,
        top_n: int = 300,
        sort_by: str = "market_cap",
        include_etf: bool = False,
    ) -> list[USStockInfo]:
        if sort_by != "market_cap":
            raise ValueError("US universe is intentionally fixed to market_cap ranking.")
        df = self.load_universe_df()
        if top_n and top_n > 0:
            df = df.head(int(top_n))

        out: list[USStockInfo] = []
        for rank, row in enumerate(df.itertuples(index=False), start=1):
            ticker = str(getattr(row, "ticker")).strip().upper()
            name = str(getattr(row, "name", ticker)).strip() or ticker
            price = _num(getattr(row, "price", None))
            volume = _num(getattr(row, "volume", None))
            trading_value = _num(getattr(row, "trading_value", None))
            if trading_value is None and price is not None and volume is not None:
                trading_value = price * volume
            source_rank = _num(getattr(row, "source_rank", None))
            out.append(
                USStockInfo(
                    ticker=ticker,
                    name=name,
                    market="US",
                    market_cap=_num(getattr(row, "market_cap", None)),
                    trading_value=trading_value,
                    volume=volume,
                    source_rank=int(source_rank) if source_rank is not None else rank,
                    exchange=str(getattr(row, "exchange", "") or ""),
                )
            )
        return out

    # MAChartAnalyzer expects .get(), while KJB/Swing expect .get_universe().
    def get(self, top_n: int = 300, sort_by: str = "market_cap") -> list[USStockInfo]:
        return self.get_universe(top_n=top_n, sort_by=sort_by, include_etf=False)

    # MA explain flow expects uppercase canonical columns.
    def load(self) -> pd.DataFrame:
        df = self.load_universe_df().copy()
        return df.rename(
            columns={
                "ticker": "Ticker",
                "name": "Name",
                "market": "Market",
                "market_cap": "시가총액",
                "volume": "거래량",
                "trading_value": "거래대금",
            }
        )
