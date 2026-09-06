from __future__ import annotations

import contextlib
import io

import pandas as pd

from .service import (
    MarketDataService,
    get_market_data_service,
    load_pykrx_stock,
    normalize_ohlcv,
    reset_krx_http_session,
)

_KRX_INDEX_CODES = {"KOSPI": "1001", "KOSDAQ": "2001"}


def get_market_index_ohlcv(
    market: str,
    start,
    end,
    *,
    service: MarketDataService | None = None,
) -> pd.DataFrame:
    """Return real index OHLCV when KRX is available, then fall back to Naver.

    MarketDataService.get_market_index currently provides a robust Naver index
    history fallback. Naver's daily index page does not expose intraday OHLC,
    so its fallback has open/high/low equal to close and is unsuitable for
    intraday-strength proxies. This wrapper first asks KRX for actual OHLC.
    """
    market_key = str(market or "").strip().upper()
    if market_key not in _KRX_INDEX_CODES:
        raise ValueError(f"지원하지 않는 시장지수: {market}")

    start_ts = pd.Timestamp(start).normalize()
    end_ts = min(pd.Timestamp(end).normalize(), pd.Timestamp.today().normalize())
    if end_ts < start_ts:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "trading_value"]
        )

    sk = start_ts.strftime("%Y%m%d")
    ek = end_ts.strftime("%Y%m%d")
    krx_code = _KRX_INDEX_CODES[market_key]

    try:
        stock = load_pykrx_stock()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            raw = stock.get_index_ohlcv_by_date(sk, ek, krx_code)
        out = normalize_ohlcv(raw)
        if not out.empty:
            return out
    except Exception as exc:
        reset_krx_http_session()
        print(
            f"[WARN] KRX {market_key} index OHLC unavailable; "
            f"using Naver close-only fallback: {type(exc).__name__}: {exc}"
        )

    svc = service or get_market_data_service()
    return svc.get_market_index(market_key, start_ts, end_ts)
