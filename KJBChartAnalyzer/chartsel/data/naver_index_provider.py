from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData.naver_index import (  # noqa: E402
    fetch_naver_index_ohlcv as _fetch_shared,
    normalize_index_code,
)


def fetch_naver_index_ohlcv(index_code: str, start_date: str, end_date: str, **kwargs):
    """Compatibility wrapper returning KJB's historical uppercase column names."""
    out = _fetch_shared(index_code, start_date, end_date, **kwargs).copy()
    return out.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "trading_value": "Trading_Value",
            "change_rate": "Change_Rate",
        }
    )[["Open", "High", "Low", "Close", "Volume", "Trading_Value", "Change_Rate"]]
