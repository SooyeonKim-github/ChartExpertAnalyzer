from __future__ import annotations

from datetime import datetime

import pandas as pd
from pykrx import stock


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    rename = {
        "시가": "Open",
        "고가": "High",
        "저가": "Low",
        "종가": "Close",
        "거래량": "Volume",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    out = out.rename(columns={c: rename.get(str(c), str(c)) for c in out.columns})
    required = ["Open", "High", "Low", "Close"]
    if any(col not in out.columns for col in required):
        return pd.DataFrame()

    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    for col in required + (["Volume"] if "Volume" in out.columns else []):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=required)
    out["MA5"] = out["Close"].rolling(5, min_periods=1).mean()
    out["MA10"] = out["Close"].rolling(10, min_periods=1).mean()
    out["MA20"] = out["Close"].rolling(20, min_periods=1).mean()
    return out


def fetch_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    ticker = str(ticker).zfill(6)
    try:
        df = _prepare(stock.get_market_ohlcv_by_date(start, end, ticker))
    except Exception as exc:
        print(f"[WARN] stock OHLCV failed {ticker}: {exc}")
        df = pd.DataFrame()

    if not df.empty:
        return df

    try:
        return _prepare(stock.get_etf_ohlcv_by_date(start, end, ticker))
    except Exception as exc:
        print(f"[WARN] ETF OHLCV failed {ticker}: {exc}")
        return pd.DataFrame()


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")
