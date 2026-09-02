from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import get_market_data_service  # noqa: E402


def load_pykrx(ticker, start, end):
    """Backward-compatible Dynamic provider backed by shared MarketData."""
    out = get_market_data_service().get_ohlcv(ticker, start, end)
    return out[["open", "high", "low", "close", "volume"]].copy()
