from __future__ import annotations

from pathlib import Path
import pandas as pd

from .base import DataProvider, normalize_ohlcv


class CSVProvider(DataProvider):
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def get_ohlcv_by_date(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        candidates = [self.data_dir / f"{ticker}.csv", self.data_dir / ticker]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise FileNotFoundError(f"{ticker} CSV를 찾을 수 없습니다: {self.data_dir}")
        df = pd.read_csv(path)
        date_col = next((c for c in df.columns if str(c).lower() in ["date", "datetime", "time", "날짜", "일자"]), None)
        if date_col is None:
            raise ValueError("CSV에 Date/날짜 컬럼이 필요합니다.")
        df[date_col] = pd.to_datetime(df[date_col])
        out = normalize_ohlcv(df.set_index(date_col))
        return out.loc[(out.index >= pd.Timestamp(start_date)) & (out.index <= pd.Timestamp(end_date))]
