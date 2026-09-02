from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import fetch_naver_index_ohlcv as _fetch_shared  # noqa: E402


def fetch_naver_index_ohlcv(index_code: str, start_date: str, end_date: str, **kwargs):
    """Compatibility wrapper returning LeaderStock's historical uppercase columns."""
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


__all__ = ["fetch_naver_index_ohlcv"]
