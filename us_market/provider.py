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


def _extract_batch_ticker(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=_REQUIRED)
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw.copy()

    target = str(ticker).strip().upper()
    for level in range(raw.columns.nlevels):
        values = list(dict.fromkeys(raw.columns.get_level_values(level)))
        actual = next((v for v in values if str(v).strip().upper() == target), None)
        if actual is not None:
            try:
                return raw.xs(actual, axis=1, level=level, drop_level=True).copy()
            except Exception:
                pass
    return pd.DataFrame(columns=_REQUIRED)


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

    def _range_key(self, ticker: str, start: str, end: str, interval: str = "1d") -> str:
        return f"{ticker}|{start}|{end}|interval={interval}|adjust={self.auto_adjust}"

    def _store_range_cache(
        self,
        ticker: str,
        start: str,
        end: str,
        out: pd.DataFrame,
        interval: str = "1d",
    ) -> None:
        key = self._range_key(ticker, start, end, interval)
        if self.use_cache:
            out.to_csv(self._cache_path(ticker, key), encoding="utf-8-sig")
        self._memory_cache[key] = out

    def _load_existing_range_cache(
        self,
        ticker: str,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> pd.DataFrame | None:
        key = self._range_key(ticker, start, end, interval)
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
        return None

    def preload_ohlcv_by_date(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        *,
        batch_size: int = 40,
        interval: str = "1d",
    ) -> dict[str, int]:
        """Bulk-download missing daily price data and prime the normal cache.

        Existing cache files are reused first. Missing tickers are downloaded in
        batches with yfinance threads enabled. Symbols that a batch cannot return
        are left missing so the normal single-ticker path can retry them later.
        """
        start = pd.Timestamp(start_date).strftime("%Y-%m-%d")
        end = pd.Timestamp(end_date).strftime("%Y-%m-%d")
        unique: list[str] = []
        seen: set[str] = set()
        for value in tickers:
            ticker = str(value or "").strip().upper()
            if ticker and ticker not in seen:
                seen.add(ticker)
                unique.append(ticker)

        ready = 0
        pending: list[str] = []
        for ticker in unique:
            cached = self._load_existing_range_cache(ticker, start, end, interval)
            if cached is not None and not cached.empty:
                ready += 1
            else:
                pending.append(ticker)

        print(
            f"[US DATA] cache ready={ready}/{len(unique)} | download needed={len(pending)}",
            flush=True,
        )
        if not pending:
            return {"total": len(unique), "ready": ready, "downloaded": 0, "failed": 0}

        yf = self._yf()
        size = max(1, int(batch_size))
        downloaded = 0
        failed = 0
        total_batches = (len(pending) + size - 1) // size
        yf_end = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        for batch_no, offset in enumerate(range(0, len(pending), size), start=1):
            batch = pending[offset: offset + size]
            batch_loaded = 0
            batch_failed = 0
            try:
                raw = yf.download(
                    tickers=batch,
                    start=start,
                    end=yf_end,
                    interval=interval,
                    auto_adjust=self.auto_adjust,
                    progress=False,
                    threads=True,
                    group_by="ticker",
                )
            except Exception as exc:
                raw = pd.DataFrame()
                print(
                    f"[US DATA][WARN] batch {batch_no}/{total_batches} download error: {exc}",
                    flush=True,
                )

            for ticker in batch:
                try:
                    piece = _extract_batch_ticker(raw, ticker)
                    out = _normalize_ohlcv(piece)
                    if out.empty:
                        raise ValueError("empty batch result")
                    self._store_range_cache(ticker, start, end, out, interval)
                    downloaded += 1
                    batch_loaded += 1
                except Exception:
                    failed += 1
                    batch_failed += 1

            ready_now = ready + downloaded
            processed = min(offset + len(batch), len(pending))
            print(
                f"[US DATA] batch {batch_no}/{total_batches} processed={processed}/{len(pending)} "
                f"loaded={batch_loaded} failed={batch_failed} ready={ready_now}/{len(unique)}",
                flush=True,
            )

        return {
            "total": len(unique),
            "ready": ready + downloaded,
            "downloaded": downloaded,
            "failed": failed,
        }

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
            key = self._range_key(ticker, start, end, interval)

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
