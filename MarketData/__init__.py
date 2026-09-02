"""Shared Korean-market data access for ChartExpertAnalyzer.

Analyzers should depend on this package rather than importing pykrx/Naver/yfinance
directly. Provider failures, cache policy, market indexes and universe construction
are centralized here so all analyzers see the same data semantics.
"""

from .liquidity import build_liquidity_universe
from .naver_index import fetch_naver_index_ohlcv
from .service import (
    MarketDataService,
    get_market_data_service,
    load_pykrx_stock,
    normalize_ohlcv,
    reset_krx_http_session,
    to_upper_ohlcv,
)
from .universe import (
    ExcelUniverseService,
    TickerInfo,
    clean_numeric_series,
    exclude_etf_rows,
    normalize_ticker,
    read_universe_excel,
)

__all__ = [
    "MarketDataService",
    "get_market_data_service",
    "load_pykrx_stock",
    "reset_krx_http_session",
    "normalize_ohlcv",
    "to_upper_ohlcv",
    "fetch_naver_index_ohlcv",
    "ExcelUniverseService",
    "TickerInfo",
    "clean_numeric_series",
    "exclude_etf_rows",
    "normalize_ticker",
    "read_universe_excel",
    "build_liquidity_universe",
]
