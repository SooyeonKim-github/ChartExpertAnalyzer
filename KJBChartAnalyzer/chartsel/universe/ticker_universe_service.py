from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List
import pandas as pd
from .excel_reader import clean_numeric_series, read_kospi_info_excel, resolve_sort_column

@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    name: str
    market: str
    market_cap: float | None = None
    trading_value: float | None = None
    volume: float | None = None
    source_rank: int | None = None

class TickerUniverseService:
    def __init__(self, info_excel_path: str | Path) -> None:
        self.info_excel_path = Path(info_excel_path)
        self._cache: pd.DataFrame | None = None

    def load_universe_df(self) -> pd.DataFrame:
        if self._cache is not None:
            return self._cache.copy()
        df = read_kospi_info_excel(self.info_excel_path)
        df['market'] = df['시장'].fillna('KOSPI').astype(str) if '시장' in df.columns else 'KOSPI'
        df = df.drop_duplicates(subset=['Ticker'], keep='first').copy()
        self._cache = df
        return df.copy()

    @staticmethod
    def _num(row: pd.Series, col: str) -> float | None:
        if col not in row.index:
            return None
        v = clean_numeric_series(pd.Series([row[col]])).iloc[0]
        return None if pd.isna(v) else float(v)

    def get_universe(self, top_n: int = 0, sort_by: str = 'market_cap', include_etf: bool = False) -> List[TickerInfo]:
        include_etf = include_etf or os.environ.get('INCLUDE_ETF', '').strip() == '1'
        df = self.load_universe_df()
        if not include_etf:
            name = df['Name'].fillna('').astype(str).str.upper()
            ticker = df['Ticker'].fillna('').astype(str).str.upper()
            market = df['market'].fillna('').astype(str).str.upper()
            etf_prefix = r'^(KODEX|TIGER|ACE|RISE|KBSTAR|SOL|PLUS|HANARO|TIMEFOLIO|KOACT|WOORI|ARIRANG|BNK|HK|VITA|히어로즈|마이다스)'
            etf_mask = market.str.contains('ETF|ETN|ETP', regex=True, na=False) | name.str.contains('ETF|ETN|ETP', regex=True, na=False) | name.str.match(etf_prefix, na=False) | ~ticker.str.fullmatch(r'\d{6}', na=False)
            df = df[~etf_mask].copy()
        if sort_by and top_n > 0:
            aliases = {'market_cap': '시가총액', 'trading_value': '거래대금', 'volume': '거래량'}
            col = resolve_sort_column(df, aliases.get(sort_by, sort_by))
            df['_sort'] = clean_numeric_series(df[col])
            df = df.sort_values('_sort', ascending=False, na_position='last')
        if top_n > 0:
            df = df.head(top_n)
        out = []
        for rank, (_, r) in enumerate(df.iterrows(), start=1):
            out.append(TickerInfo(str(r['Ticker']).zfill(6), str(r['Name']), str(r.get('market', 'KOSPI')).upper(), self._num(r, '시가총액'), self._num(r, '거래대금'), self._num(r, '거래량'), rank))
        return out
