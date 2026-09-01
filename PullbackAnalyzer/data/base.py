from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class DataProvider(ABC):
    @abstractmethod
    def get_ohlcv_by_date(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    rename = {
        "시가": "Open", "고가": "High", "저가": "Low", "종가": "Close", "거래량": "Volume",
        "거래대금": "Trading_Value", "등락률": "Change_Rate",
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
        "trading_value": "Trading_Value", "change_rate": "Change_Rate",
    }
    raw = df.rename(columns=rename).copy()
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"OHLCV 필수 컬럼 누락: {missing}")
    keep = REQUIRED_COLUMNS + [c for c in ("Trading_Value", "Change_Rate") if c in raw.columns]
    out = raw[keep].copy()
    for c in keep:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out.index = pd.to_datetime(out.index)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.dropna(subset=["Open", "High", "Low", "Close"]).copy()
