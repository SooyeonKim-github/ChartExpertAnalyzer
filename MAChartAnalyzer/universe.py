from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
from config import DEFAULT_INFO_EXCEL

TICKER_COLUMNS = ['종목코드', '단축코드', 'Ticker', 'ticker', 'Code', 'code']
NAME_COLUMNS = ['종목명', '한글 종목약명', '한글 종목명', 'Name', 'name']
SORT_ALIASES = {'market_cap': '시가총액', 'trading_value': '거래대금', 'volume': '거래량'}

@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    name: str
    market: str

def _ticker(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip().upper()
    if text.endswith('.0'):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else None

def _numeric(s):
    return pd.to_numeric(s.astype(str).str.replace(',', '', regex=False).str.replace('%', '', regex=False).str.replace('N/A', '', regex=False).str.strip(), errors='coerce')

class TickerUniverse:
    def __init__(self, info_excel: str | Path = DEFAULT_INFO_EXCEL):
        self.info_excel = Path(info_excel)

    def load(self):
        if not self.info_excel.exists():
            raise FileNotFoundError(f'종목 Universe Excel을 찾을 수 없습니다: {self.info_excel}')
        df = pd.read_excel(self.info_excel, dtype=str)
        tc = next((c for c in TICKER_COLUMNS if c in df.columns), None)
        nc = next((c for c in NAME_COLUMNS if c in df.columns), None)
        if tc is None:
            raise ValueError(f'종목코드 컬럼을 찾지 못했습니다: {list(df.columns)}')
        nc = nc or tc
        out = df.copy()
        out['Ticker'] = out[tc].map(_ticker)
        out['Name'] = out[nc].fillna('').astype(str).str.strip()
        out['Market'] = out['시장'].fillna('KOSPI').astype(str) if '시장' in out.columns else 'KOSPI'
        out = out[out['Ticker'].notna()].drop_duplicates('Ticker', keep='first')
        out['Name'] = out['Name'].where(out['Name'].ne(''), out['Ticker'])
        if os.environ.get('INCLUDE_ETF', '').strip() != '1':
            name = out['Name'].fillna('').astype(str).str.upper()
            market = out['Market'].fillna('').astype(str).str.upper()
            prefix = r'^(KODEX|TIGER|ACE|RISE|KBSTAR|SOL|PLUS|HANARO|TIMEFOLIO|KOACT|WOORI|ARIRANG|BNK|HK|VITA|히어로즈|마이다스)'
            out = out[~(market.str.contains('ETF|ETN|ETP', regex=True, na=False) | name.str.contains('ETF|ETN|ETP', regex=True, na=False) | name.str.match(prefix, na=False))].copy()
        return out

    def get(self, top_n=0, sort_by='market_cap'):
        df = self.load()
        if top_n > 0:
            col = SORT_ALIASES.get(sort_by)
            if col is None or col not in df.columns:
                raise ValueError(f'정렬 기준 컬럼 없음: {sort_by}')
            df['_sort'] = _numeric(df[col])
            df = df.sort_values('_sort', ascending=False).head(top_n)
        return [TickerInfo(str(r['Ticker']).zfill(6), str(r['Name']), str(r['Market'])) for _, r in df.iterrows()]
