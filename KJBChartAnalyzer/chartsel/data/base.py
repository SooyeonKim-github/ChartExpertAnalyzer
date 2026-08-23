from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd

REQUIRED_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']

class DataProvider(ABC):
    @abstractmethod
    def get_ohlcv(self, ticker: str, period: str = '2y', interval: str = '1d') -> pd.DataFrame:
        raise NotImplementedError

def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    rename_map = {c.lower(): c for c in REQUIRED_COLUMNS}
    fixed = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in rename_map:
            fixed[col] = rename_map[key]
    df = df.rename(columns=fixed).copy()
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f'OHLCV 필수 컬럼 누락: {missing}')
    df = df[REQUIRED_COLUMNS].dropna(subset=['Open','High','Low','Close'])
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df
