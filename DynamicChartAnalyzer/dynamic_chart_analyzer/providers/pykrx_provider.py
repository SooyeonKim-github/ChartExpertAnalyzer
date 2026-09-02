from __future__ import annotations

import contextlib
import hashlib
import io
import sys
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
_MEMORY_CACHE: dict[str, pd.DataFrame] = {}

_INDEX_ALIASES = {
    "^KS11": "1001",
    "KOSPI": "1001",
    "^KQ11": "2001",
    "KOSDAQ": "2001",
    "1001": "1001",
    "2001": "2001",
}


def _normalize_ohlcv(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    out = df.rename(
        columns={
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    ).copy()
    needed = ["open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in out.columns]
    if missing:
        raise ValueError(f"OHLCV columns missing: {missing}; columns={list(df.columns)}")
    out = out[needed]
    for c in needed:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out.index = pd.to_datetime(out.index)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.dropna(subset=["open", "high", "low", "close"]).copy()


def _cache_path(ticker, start, end):
    digest = hashlib.md5(f"{ticker}_{start}_{end}".encode()).hexdigest()[:10]
    return CACHE_DIR / f"{ticker}_{digest}.csv"


def _load_naver_index(code: str, start: str, end: str) -> pd.DataFrame:
    repo_root = Path(__file__).resolve().parents[3]
    kjb_root = repo_root / "KJBChartAnalyzer"
    if str(kjb_root) not in sys.path:
        sys.path.insert(0, str(kjb_root))
    from chartsel.data.naver_index_provider import fetch_naver_index_ohlcv

    return _normalize_ohlcv(fetch_naver_index_ohlcv(code, start, end))


def _load_stock_pykrx(code: str, start: str, end: str) -> pd.DataFrame:
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx is not installed. Run: pip install pykrx") from exc

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        out = _normalize_ohlcv(stock.get_market_ohlcv_by_date(start, end, code, adjusted=True))
        if out.empty:
            out = _normalize_ohlcv(stock.get_etf_ohlcv_by_date(start, end, code))
    return out


def load_pykrx(ticker, start, end):
    raw_code = str(ticker).strip().upper()
    is_index = raw_code in _INDEX_ALIASES
    if is_index:
        code = _INDEX_ALIASES[raw_code]
        cache_code = f"INDEX_{code}"
    else:
        code = raw_code
        if code.endswith(".KS") or code.endswith(".KQ"):
            code = code[:-3]
        if code.isdigit():
            code = code.zfill(6)
        cache_code = code

    start_ts = pd.Timestamp(start).normalize()
    requested_end = pd.Timestamp(end).normalize()
    end_ts = min(requested_end, pd.Timestamp.today().normalize())
    if end_ts < start_ts:
        raise RuntimeError(f"Requested OHLCV range is entirely in the future: ticker={code}")

    sk = start_ts.strftime("%Y%m%d")
    ek = end_ts.strftime("%Y%m%d")
    key = f"{cache_code}:{sk}:{ek}"
    if key in _MEMORY_CACHE:
        return _MEMORY_CACHE[key].copy()

    path = _cache_path(cache_code, sk, ek)
    if path.exists():
        out = _normalize_ohlcv(pd.read_csv(path, index_col=0, parse_dates=True))
        if not out.empty:
            _MEMORY_CACHE[key] = out
            return out.copy()

    if is_index:
        # KRX index endpoints are unstable under the current pykrx/KRX session policy.
        # Reuse the KJB Naver index provider, which supplies the Close/Volume series
        # required by Dynamic market-regime and relative-strength features.
        out = _load_naver_index(code, sk, ek)
    else:
        out = _load_stock_pykrx(code, sk, ek)

    if out.empty:
        kind = "index" if is_index else "ticker"
        raise RuntimeError(f"No OHLCV returned for {kind}={code}, range={sk}~{ek}")
    out.to_csv(path, encoding="utf-8-sig")
    _MEMORY_CACHE[key] = out
    return out.copy()
