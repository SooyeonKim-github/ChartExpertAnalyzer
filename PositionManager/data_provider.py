from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import get_market_data_service, to_upper_ohlcv  # noqa: E402


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = to_upper_ohlcv(df)
    out["MA5"] = out["Close"].rolling(5, min_periods=1).mean()
    out["MA10"] = out["Close"].rolling(10, min_periods=1).mean()
    out["MA20"] = out["Close"].rolling(20, min_periods=1).mean()
    return out


def fetch_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    try:
        return _prepare(get_market_data_service().get_ohlcv(str(ticker).zfill(6), start, end))
    except Exception as exc:
        print(f"[WARN] shared MarketData OHLCV failed {str(ticker).zfill(6)}: {exc}")
        return pd.DataFrame()


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")
