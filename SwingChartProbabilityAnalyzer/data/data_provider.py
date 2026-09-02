from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from config import CACHE_DIR

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import MarketDataService, to_upper_ohlcv  # noqa: E402


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = to_upper_ohlcv(df)
    return out[["Open", "High", "Low", "Close", "Volume"]]


class PykrxDataProvider:
    """Swing compatibility adapter over shared MarketData."""

    def __init__(self, cache_dir: Path = CACHE_DIR, use_cache: bool = True) -> None:
        self.service = MarketDataService(cache_dir=cache_dir, use_cache=use_cache)

    def get_ohlcv(self, ticker, start_date, end_date):
        return normalize_ohlcv(self.service.get_ohlcv(ticker, start_date, end_date))
