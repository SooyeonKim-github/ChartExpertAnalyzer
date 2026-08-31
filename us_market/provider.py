from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd


_REQUIRED = ["Open", "High", "Low", "Close", "Volume"]


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_REQUIRED)

    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            col[0] if isinstance(col, tuple) else col
            for col in out.columns
        ]

    rename = {}
    for col in out.columns:
        key = str(col).strip().lower()
        if key == "open":
            rename[col] = "Open"
        elif key == "high":
            rename[col] = "High"
        elif key == "low":
            rename[col] = "Low"
        elif key == "close":
            rename[col] = "Close"
        elif key == "volume":
            rename[col] = "Volume"
    out = out.rename(columns=rename)

    missing = [c for c in _REQUIRED if c not in out.columns]
    if missing:
        raise ValueError(f"US OHLCV required columns missing: {missing}; columns={list(df.columns)}")

    out = out[_REQUIRED].copy()
    for col in _REQUIRED:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()]
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.dropna(subset=["Open", "High", "Low", "Close"]).copy()


class USYFinanceProvider:
    """Cached Yahoo Finance daily OHLCV provider for US stocks and indexes.

    Prices are auto-adjusted so historical split/dividend events do not create
    artificial chart gaps. Yahoo's end date is exclusive, therefore date-range
    requests add one calendar day internally.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        use_cache: bool = True,
        auto_adjust: bool = True,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        self.cache_dir = Path(cache_dir) if cache_dir else root / "cache" / "us_yfinance"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = bool(use_cache)
        self.auto_adjust = bool(auto_adjust)
        self._memory_cache: dict[str, pd.DataFrame] = {}

    @staticmethod
    def _yf():
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "yfinance is required for US data. Install/upgrade with: "
                "python -m pip install -U yfinance"
            ) from exc
        return yf

    @staticmethod
    def _safe_ticker(ticker: str) -> str:
        return re.sub(r"[^0-9A-Za-z.^_-]+", "_", str(ticker).strip().upper())

    def _cache_path(self, ticker: str, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return self.cache_dir / f"{self._safe_ticker(ticker)}_{digest}.csv"

    def _download(
        self,
        ticker: str,
        *,
        start: str | None = None,
        end: str | None = None,
        period: str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        yf = self._yf()
        kwargs = {
            "tickers": ticker,
            "interval": interval,
            "auto_adjust": self.auto_adjust,
            "progress": False,
            "threads": False,
        }
        if period:
            kwargs["period"] = period
        else:
            kwargs["start"] = start
            if end:
                # yfinance treats end as exclusive.
                kwargs["end"] = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        raw = yf.download(**kwargs)
        out = _normalize_ohlcv(raw)
        if out.empty:
            raise ValueError(f"No Yahoo Finance OHLCV data: {ticker}")
        return out

    def get_ohlcv(
        self,
        ticker: str,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        period: str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        # Compatibility with both project call styles:
        # get_ohlcv("AAPL", "2025-01-01", "2026-01-01")
        # get_ohlcv("AAPL", period="5y")
        # get_ohlcv("AAPL", "5y")
        if period is None and start_date and end_date is None:
            text = str(start_date).strip().lower()
            if re.fullmatch(r"\d+(d|wk|mo|y)", text) or text in {"max", "ytd"}:
                period = text
                start_date = None
        if period is None and start_date is None:
            period = "5y"

        if period:
            key = f"{ticker}|period={period}|interval={interval}|adjust={self.auto_adjust}"
        else:
            start = pd.Timestamp(start_date).strftime("%Y-%m-%d")
            end = pd.Timestamp(end_date).strftime("%Y-%m-%d")
            key = f"{ticker}|{start}|{end}|interval={interval}|adjust={self.auto_adjust}"

        if key in self._memory_cache:
            return self._memory_cache[key].copy()

        cache_path = self._cache_path(ticker, key)
        if self.use_cache and cache_path.exists():
            try:
                cached = _normalize_ohlcv(pd.read_csv(cache_path, index_col=0, parse_dates=True))
                if not cached.empty:
                    self._memory_cache[key] = cached
                    return cached.copy()
            except Exception:
                pass

        if period:
            out = self._download(ticker, period=period, interval=interval)
        else:
            out = self._download(
                ticker,
                start=pd.Timestamp(start_date).strftime("%Y-%m-%d"),
                end=pd.Timestamp(end_date).strftime("%Y-%m-%d"),
                interval=interval,
            )

        if self.use_cache:
            out.to_csv(cache_path, encoding="utf-8-sig")
        self._memory_cache[key] = out
        return out.copy()

    def get_ohlcv_by_date(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self.get_ohlcv(ticker, start_date, end_date)
