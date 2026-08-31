from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
_MEMORY_CACHE: dict[str, pd.DataFrame] = {}


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    out = df.rename(columns={
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
    }).copy()

    needed = ["open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in out.columns]
    if missing:
        raise ValueError(f"OHLCV columns missing: {missing}; columns={list(df.columns)}")

    out = out[needed]
    for col in needed:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out.index = pd.to_datetime(out.index)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.dropna(subset=["open", "high", "low", "close"]).copy()


def _cache_path(ticker: str, start: str, end: str) -> Path:
    raw = f"{ticker}_{start}_{end}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return CACHE_DIR / f"{ticker}_{digest}.csv"


def load_pykrx(ticker: str, start: str, end: str):
    """Load one KRX stock with the same per-ticker flow used by Swing/KJB analyzers.

    - Uses only get_market_ohlcv_by_date for stocks.
    - Requests adjusted prices.
    - Never asks pykrx for dates later than today.
    - Reuses memory/file cache to reduce repeated KRX calls during range backtests.
    """
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx is not installed. Run: pip install pykrx") from exc

    code = str(ticker).strip().upper()
    if code.endswith(".KS") or code.endswith(".KQ"):
        code = code[:-3]
    if code.isdigit():
        code = code.zfill(6)

    start_ts = pd.Timestamp(start).normalize()
    requested_end = pd.Timestamp(end).normalize()
    end_ts = min(requested_end, pd.Timestamp.today().normalize())
    if end_ts < start_ts:
        raise RuntimeError(
            f"Requested OHLCV range is entirely in the future: ticker={code}, "
            f"range={start_ts.date()}~{requested_end.date()}"
        )

    start_key = start_ts.strftime("%Y%m%d")
    end_key = end_ts.strftime("%Y%m%d")
    key = f"{code}:{start_key}:{end_key}"

    if key in _MEMORY_CACHE:
        return _MEMORY_CACHE[key].copy()

    cache_path = _cache_path(code, start_key, end_key)
    if cache_path.exists():
        cached = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        out = _normalize_ohlcv(cached)
        if not out.empty:
            _MEMORY_CACHE[key] = out
            return out.copy()

    raw = stock.get_market_ohlcv_by_date(
        start_key,
        end_key,
        code,
        adjusted=True,
    )
    out = _normalize_ohlcv(raw)
    if out.empty:
        raise RuntimeError(
            f"No OHLCV returned for ticker={code}, range={start_key}~{end_key}"
        )

    out.to_csv(cache_path, encoding="utf-8-sig")
    _MEMORY_CACHE[key] = out
    return out.copy()
