from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from ..utils.date_utils import period_to_date_range

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import MarketDataService, to_upper_ohlcv  # noqa: E402


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = to_upper_ohlcv(df)
    if "Change_Rate" not in out.columns:
        out["Change_Rate"] = pd.to_numeric(out["Close"], errors="coerce").pct_change() * 100.0
    return out[["Open", "High", "Low", "Close", "Volume", "Trading_Value", "Change_Rate"]]


class PykrxDataProvider:
    """Backward-compatible KJB adapter over the shared MarketData service."""

    def __init__(self, cache_dir: str | Path | None = None, use_cache: bool = True, end_date: str | None = None) -> None:
        self.service = MarketDataService(cache_dir=cache_dir, use_cache=use_cache) if cache_dir else MarketDataService(use_cache=use_cache)
        self.end_date = end_date

    @staticmethod
    def normalize_ticker(ticker: str) -> str:
        return MarketDataService.normalize_ticker(ticker)

    def get_ohlcv_by_date(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        out = self.service.get_ohlcv(ticker, start_date, end_date)
        return normalize_ohlcv(out)

    def get_ohlcv(self, ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        if interval != "1d":
            raise ValueError("PykrxDataProvider는 현재 일봉(1d)만 지원합니다.")
        start_date, end_date = period_to_date_range(period, self.end_date)
        out = self.get_ohlcv_by_date(ticker, start_date, end_date)
        if out.empty:
            raise ValueError(f"데이터 없음: {ticker} ({start_date}~{end_date})")
        return out.copy()
