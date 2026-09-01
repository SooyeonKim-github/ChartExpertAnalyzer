from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict
import pandas as pd

from config import CACHE_DIR
from .base import DataProvider, normalize_ohlcv
from .naver_index_provider import fetch_naver_index_ohlcv

_INDEX_ALIASES = {
    "^KS11": "KOSPI", "KOSPI": "KOSPI", "1001": "KOSPI",
    "^KQ11": "KOSDAQ", "KOSDAQ": "KOSDAQ", "2001": "KOSDAQ",
}


class PykrxDataProvider(DataProvider):
    """Stocks via pykrx; KOSPI/KOSDAQ index via Naver index day pages."""

    def __init__(self, cache_dir: str | Path | None = None, use_cache: bool = True) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self._memory_cache: Dict[str, pd.DataFrame] = {}

    @staticmethod
    def _load_pykrx():
        try:
            from pykrx import stock
        except ImportError as exc:
            raise RuntimeError("pykrx가 필요합니다. pip install -r requirements.txt") from exc
        return stock

    @staticmethod
    def normalize_ticker(ticker: str) -> str:
        text = str(ticker).strip().upper()
        if text.endswith(".KS") or text.endswith(".KQ"):
            text = text[:-3]
        return text.zfill(6) if text.isdigit() else text

    def _cache_path(self, ticker: str, start_date: str, end_date: str, kind: str) -> Path:
        safe = str(ticker).replace("^", "").replace("/", "_")
        digest = hashlib.md5(f"{kind}_{ticker}_{start_date}_{end_date}".encode("utf-8")).hexdigest()[:10]
        return self.cache_dir / f"{safe}_{digest}.csv"

    def get_ohlcv_by_date(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        alias = str(ticker).strip().upper()
        kind = "naver_index" if alias in _INDEX_ALIASES else "stock"
        key = f"{kind}:{alias}:{start_date}:{end_date}"
        if key in self._memory_cache:
            return self._memory_cache[key].copy()
        path = self._cache_path(alias, start_date, end_date, kind)
        if self.use_cache and path.exists():
            out = normalize_ohlcv(pd.read_csv(path, index_col=0, parse_dates=True))
            self._memory_cache[key] = out
            return out.copy()

        if alias in _INDEX_ALIASES:
            out = normalize_ohlcv(fetch_naver_index_ohlcv(_INDEX_ALIASES[alias], start_date, end_date))
        else:
            stock = self._load_pykrx()
            start = pd.Timestamp(start_date).strftime("%Y%m%d")
            end = pd.Timestamp(end_date).strftime("%Y%m%d")
            code = self.normalize_ticker(alias)
            out = normalize_ohlcv(stock.get_market_ohlcv_by_date(start, end, code, adjusted=True))

        if self.use_cache and not out.empty:
            out.to_csv(path, encoding="utf-8-sig")
        self._memory_cache[key] = out
        return out.copy()
