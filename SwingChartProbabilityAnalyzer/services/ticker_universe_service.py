from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

from config import INFO_EXCEL_PATH
from utils.excel_reader import clean_numeric_series, read_kospi_info_excel, resolve_sort_column


@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    name: str
    market: str


class TickerUniverseService:
    """KOSPI_Info.xlsx는 '분석 대상 목록'에만 사용한다. 재무/수급값은 신호에 사용하지 않는다."""

    def __init__(self, info_excel_path: str | Path = INFO_EXCEL_PATH) -> None:
        self.info_excel_path = Path(info_excel_path)
        self._cache: pd.DataFrame | None = None

    def load_universe_df(self) -> pd.DataFrame:
        if self._cache is not None:
            return self._cache.copy()
        df = read_kospi_info_excel(self.info_excel_path)
        df["market"] = df["시장"].fillna("KOSPI").astype(str) if "시장" in df.columns else "KOSPI"
        df = df.drop_duplicates(subset=["Ticker"], keep="first").copy()
        self._cache = df
        return df.copy()

    def get_universe(self, top_n: int = 0, sort_by: str = "market_cap", include_etf: bool = False) -> List[TickerInfo]:
        df = self.load_universe_df()
        if not include_etf:
            name = df["Name"].fillna("").astype(str).str.upper()
            ticker = df["Ticker"].fillna("").astype(str).str.upper()
            market = df["market"].fillna("").astype(str).str.upper()
            etf_prefix = r"^(KODEX|TIGER|ACE|RISE|KBSTAR|SOL|PLUS|HANARO|TIMEFOLIO|KOACT|WOORI|ARIRANG|BNK|HK|VITA|히어로즈|마이다스)"
            etf_mask = (market.str.contains("ETF|ETN|ETP", regex=True, na=False)
                        | name.str.contains("ETF|ETN|ETP", regex=True, na=False)
                        | name.str.match(etf_prefix, na=False)
                        | ~ticker.str.fullmatch(r"\d{6}", na=False))
            df = df[~etf_mask].copy()
        if sort_by and top_n > 0:
            aliases = {"market_cap": "시가총액", "trading_value": "거래대금", "volume": "거래량"}
            col = resolve_sort_column(df, aliases.get(sort_by, sort_by))
            df["_sort"] = clean_numeric_series(df[col])
            df = df.sort_values("_sort", ascending=False)
        if top_n > 0:
            df = df.head(top_n)
        return [TickerInfo(str(r["Ticker"]).zfill(6), str(r["Name"]), str(r.get("market", "KOSPI"))) for _, r in df.iterrows()]
