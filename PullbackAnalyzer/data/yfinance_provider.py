from __future__ import annotations

import pandas as pd
from .base import DataProvider, normalize_ohlcv


class YFinanceProvider(DataProvider):
    def get_ohlcv_by_date(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        import yfinance as yf
        end_exclusive = (pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        df = yf.download(
            ticker, start=pd.Timestamp(start_date).strftime("%Y-%m-%d"), end=end_exclusive,
            interval="1d", auto_adjust=False, progress=False, threads=False,
        )
        if df.empty:
            raise ValueError(f"데이터 없음: {ticker}")
        return normalize_ohlcv(df)
