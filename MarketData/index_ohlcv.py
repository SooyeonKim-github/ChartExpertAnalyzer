from __future__ import annotations

import contextlib
import io

import pandas as pd

from .service import MarketDataService, get_market_data_service, load_pykrx_stock, normalize_ohlcv, reset_krx_http_session

_KRX_INDEX_CODES = {"KOSPI": "1001", "KOSDAQ": "2001"}
_YF_INDEX_CODES = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}


def _yfinance_index_ohlcv(market: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            raw = yf.download(_YF_INDEX_CODES[market], start=start.strftime("%Y-%m-%d"), end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), progress=False, auto_adjust=False, threads=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        if raw is None or raw.empty:
            return pd.DataFrame()
        if "Volume" not in raw.columns:
            raw["Volume"] = 0.0
        return normalize_ohlcv(raw)
    except Exception:
        return pd.DataFrame()


def get_market_index_ohlcv(market: str, start, end, *, service: MarketDataService | None = None) -> pd.DataFrame:
    """Actual daily-range priority: KRX -> Yahoo Finance -> Naver close-only."""
    market_key = str(market or "").strip().upper()
    if market_key not in _KRX_INDEX_CODES:
        raise ValueError(f"지원하지 않는 시장지수: {market}")
    start_ts = pd.Timestamp(start).normalize()
    end_ts = min(pd.Timestamp(end).normalize(), pd.Timestamp.today().normalize())
    if end_ts < start_ts:
        return pd.DataFrame(columns=["open","high","low","close","volume","trading_value"])
    sk, ek = start_ts.strftime("%Y%m%d"), end_ts.strftime("%Y%m%d")
    try:
        stock = load_pykrx_stock()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            raw = stock.get_index_ohlcv_by_date(sk, ek, _KRX_INDEX_CODES[market_key])
        out = normalize_ohlcv(raw)
        if not out.empty:
            out.attrs["source_mode"] = "KRX_INDEX_OHLC"
            return out
    except Exception as exc:
        reset_krx_http_session()
        print(f"[WARN] KRX {market_key} index OHLC unavailable: {type(exc).__name__}: {exc}")
    out = _yfinance_index_ohlcv(market_key, start_ts, end_ts)
    if not out.empty:
        out.attrs["source_mode"] = "YFINANCE_INDEX_OHLC"
        print(f"[INFO] {market_key} index OHLC source=YFINANCE_INDEX_OHLC")
        return out
    print(f"[WARN] {market_key} actual index OHLC unavailable; using Naver close-only fallback.")
    svc = service or get_market_data_service()
    out = svc.get_market_index(market_key, start_ts, end_ts)
    out.attrs["source_mode"] = "NAVER_CLOSE_ONLY"
    return out
