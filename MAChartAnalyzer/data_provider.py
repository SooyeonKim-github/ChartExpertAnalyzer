from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Dict
import pandas as pd
from config import CACHE_DIR

def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=['Open','High','Low','Close','Volume'])
    out = df.rename(columns={'시가':'Open','고가':'High','저가':'Low','종가':'Close','거래량':'Volume','open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'}).copy()
    needed=['Open','High','Low','Close','Volume']
    missing=[c for c in needed if c not in out.columns]
    if missing:
        raise ValueError(f'OHLCV 컬럼 누락: {missing}; columns={list(df.columns)}')
    out=out[needed]
    for c in needed:
        out[c]=pd.to_numeric(out[c],errors='coerce')
    out.index=pd.to_datetime(out.index)
    out=out[~out.index.duplicated(keep='last')].sort_index()
    return out.dropna(subset=['Open','High','Low','Close']).copy()

class PykrxDataProvider:
    def __init__(self, cache_dir: Path = CACHE_DIR, use_cache: bool = True) -> None:
        self.cache_dir=Path(cache_dir); self.cache_dir.mkdir(parents=True,exist_ok=True); self.use_cache=use_cache; self._memory_cache:Dict[str,pd.DataFrame]={}
    @staticmethod
    def _stock():
        try:
            from pykrx import stock
        except ImportError as exc:
            raise RuntimeError('pykrx가 필요합니다. pip install -r requirements.txt') from exc
        return stock
    def _cache_path(self,ticker,start_date,end_date):
        digest=hashlib.md5(f'{ticker}_{start_date}_{end_date}'.encode()).hexdigest()[:10]
        return self.cache_dir/f'{ticker}_{digest}.csv'
    def get_ohlcv(self,ticker,start_date,end_date):
        key=f'{ticker}:{start_date}:{end_date}'
        if key in self._memory_cache:
            return self._memory_cache[key].copy()
        path=self._cache_path(ticker,start_date,end_date)
        if self.use_cache and path.exists():
            out=normalize_ohlcv(pd.read_csv(path,index_col=0,parse_dates=True)); self._memory_cache[key]=out; return out.copy()
        stock=self._stock(); start=pd.Timestamp(start_date).strftime('%Y%m%d'); end=pd.Timestamp(end_date).strftime('%Y%m%d'); code=str(ticker).zfill(6)
        out=normalize_ohlcv(stock.get_market_ohlcv_by_date(start,end,code,adjusted=True))
        if out.empty:
            out=normalize_ohlcv(stock.get_etf_ohlcv_by_date(start,end,code))
        if self.use_cache and not out.empty:
            out.to_csv(path,encoding='utf-8-sig')
        self._memory_cache[key]=out
        return out.copy()
