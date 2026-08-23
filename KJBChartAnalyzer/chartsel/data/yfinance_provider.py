from __future__ import annotations
import pandas as pd
from .base import DataProvider, normalize_ohlcv

class YFinanceProvider(DataProvider):
    def get_ohlcv(self, ticker: str, period: str = '2y', interval: str = '1d') -> pd.DataFrame:
        import yfinance as yf
        df = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False, threads=False)
        if df.empty:
            raise ValueError(f'데이터 없음: {ticker}')
        return normalize_ohlcv(df)
