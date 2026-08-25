from __future__ import annotations

import pandas as pd
from core.indicators import add_indicators, normalize_ohlcv


class PyKrxDataProvider:
    def __init__(self) -> None:
        try:
            from pykrx import stock
        except Exception as exc:
            raise RuntimeError("pykrx is required. Run: pip install -r requirements.txt") from exc
        self.stock = stock

    def stock_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        raw = self.stock.get_market_ohlcv_by_date(start, end, ticker)
        return add_indicators(raw) if raw is not None and len(raw) else pd.DataFrame()

    def index_ohlcv(self, index_ticker: str, start: str, end: str) -> pd.DataFrame:
        try: raw = self.stock.get_index_ohlcv_by_date(start, end, index_ticker)
        except Exception: return pd.DataFrame()
        return normalize_ohlcv(raw) if raw is not None and len(raw) else pd.DataFrame()

    def ticker_name(self, ticker: str) -> str:
        try: return str(self.stock.get_market_ticker_name(ticker))
        except Exception: return ticker

    def market_cap(self, date: str, market: str) -> pd.DataFrame:
        try: raw = self.stock.get_market_cap_by_ticker(date, market=market)
        except Exception: return pd.DataFrame()
        if raw is None or len(raw) == 0: return pd.DataFrame()
        out = raw.copy(); rename = {}
        for col in out.columns:
            if "시가총액" in str(col) or ("market" in str(col).lower() and "cap" in str(col).lower()): rename[col] = "market_cap"
        out = out.rename(columns=rename)
        if "market_cap" not in out: return pd.DataFrame()
        out["ticker"] = out.index.astype(str).str.zfill(6)
        return out[["ticker","market_cap"]].reset_index(drop=True)

    def trading_dates(self, start: str, end: str, index_ticker: str = "1001") -> list[str]:
        df = self.index_ohlcv(index_ticker, start, end)
        return [pd.Timestamp(x).strftime("%Y%m%d") for x in df.index] if not df.empty else []

    def future_closes(self, ticker: str, signal_date: str, calendar_days: int = 130) -> pd.Series:
        start = pd.Timestamp(signal_date); end = start + pd.Timedelta(days=calendar_days); df = self.stock_ohlcv(ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        return df["close"] if not df.empty else pd.Series(dtype=float)
