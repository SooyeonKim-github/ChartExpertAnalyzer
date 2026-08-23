from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict

import pandas as pd

from .base import DataProvider, normalize_ohlcv as normalize_base
from .naver_index_provider import fetch_naver_index_ohlcv
from ..utils.date_utils import period_to_date_range


_INDEX_ALIASES = {
    '^KS11': 'KOSPI', 'KOSPI': 'KOSPI', '1001': 'KOSPI',
    '^KQ11': 'KOSDAQ', 'KOSDAQ': 'KOSDAQ', '2001': 'KOSDAQ',
}


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """pykrx OHLCV를 표준화하되 V3 섹터 분석용 거래대금/등락률은 보존한다."""
    if df is None or df.empty:
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume', 'Trading_Value', 'Change_Rate'])
    rename = {
        '시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume',
        '거래대금': 'Trading_Value', '등락률': 'Change_Rate',
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume',
        'trading_value': 'Trading_Value', 'change_rate': 'Change_Rate',
    }
    raw = df.rename(columns=rename).copy()
    extras = {}
    for col in ['Trading_Value', 'Change_Rate']:
        if col in raw.columns:
            extras[col] = pd.to_numeric(raw[col], errors='coerce').copy()
    try:
        out = normalize_base(raw)
    except ValueError:
        needed = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing = [c for c in needed if c not in raw.columns]
        if missing:
            raise ValueError(f'OHLCV 컬럼 누락: {missing}; columns={list(df.columns)}')
        out = raw[needed].copy()
        for c in needed:
            out[c] = pd.to_numeric(out[c], errors='coerce')
        out.index = pd.to_datetime(out.index)
        out = out[~out.index.duplicated(keep='last')].sort_index()
        out = out.dropna(subset=['Open', 'High', 'Low', 'Close']).copy()
    for col, values in extras.items():
        values.index = pd.to_datetime(values.index)
        out[col] = values.reindex(out.index)
    return out


class PykrxDataProvider(DataProvider):
    """개별 종목은 pykrx, KOSPI/KOSDAQ 지수는 네이버 금융을 사용하는 OHLCV 제공자."""

    def __init__(self, cache_dir: str | Path | None = None, use_cache: bool = True, end_date: str | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.cache_dir = Path(cache_dir) if cache_dir else root / 'cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self.end_date = end_date
        self._memory_cache: Dict[str, pd.DataFrame] = {}

    @staticmethod
    def _load_pykrx():
        try:
            from pykrx import stock
        except ImportError as exc:
            raise RuntimeError('pykrx가 필요합니다. pip install -r requirements.txt') from exc
        return stock

    @staticmethod
    def normalize_ticker(ticker: str) -> str:
        text = str(ticker).strip().upper()
        if text.endswith('.KS') or text.endswith('.KQ'):
            text = text[:-3]
        return text.zfill(6) if text.isdigit() else text

    def _cache_path(self, ticker: str, start_date: str, end_date: str, kind: str) -> Path:
        safe = str(ticker).replace('^', '').replace('/', '_')
        raw = f'{kind}_{ticker}_{start_date}_{end_date}'
        digest = hashlib.md5(raw.encode('utf-8')).hexdigest()[:10]
        return self.cache_dir / f'{safe}_{digest}.csv'

    def _fetch_range(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        alias = str(ticker).strip().upper()

        # 시장지수는 pykrx index endpoint를 사용하지 않는다.
        # KRX 로그인/응답 오류를 피하기 위해 네이버 금융 일별시세를 전용 소스로 사용한다.
        if alias in _INDEX_ALIASES:
            code = _INDEX_ALIASES[alias]
            try:
                return fetch_naver_index_ohlcv(code, start_date, end_date)
            except Exception as exc:
                raise RuntimeError(
                    f'네이버 시장지수 조회 실패: {code} ({start_date}~{end_date})'
                ) from exc

        # 개별 종목만 pykrx 사용.
        stock = self._load_pykrx()
        start = pd.Timestamp(start_date).strftime('%Y%m%d')
        end = pd.Timestamp(end_date).strftime('%Y%m%d')
        code = self.normalize_ticker(alias)
        raw = stock.get_market_ohlcv_by_date(start, end, code, adjusted=True)
        return normalize_ohlcv(raw)

    def get_ohlcv_by_date(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        alias = str(ticker).strip().upper()
        # 예전 pykrx/yfinance 지수 캐시와 네이버 지수 캐시가 섞이지 않도록 cache kind를 분리한다.
        kind = 'naver_index' if alias in _INDEX_ALIASES else 'stock'
        key = f'{kind}:{alias}:{start_date}:{end_date}'
        if key in self._memory_cache:
            return self._memory_cache[key].copy()
        cache_path = self._cache_path(alias, start_date, end_date, kind)
        if self.use_cache and cache_path.exists():
            out = normalize_ohlcv(pd.read_csv(cache_path, index_col=0, parse_dates=True))
            self._memory_cache[key] = out
            return out.copy()
        out = self._fetch_range(alias, start_date, end_date)
        if self.use_cache and not out.empty:
            out.to_csv(cache_path, encoding='utf-8-sig')
        self._memory_cache[key] = out
        return out.copy()

    def get_ohlcv(self, ticker: str, period: str = '2y', interval: str = '1d') -> pd.DataFrame:
        if interval != '1d':
            raise ValueError('PykrxDataProvider는 현재 일봉(1d)만 지원합니다.')
        start_date, end_date = period_to_date_range(period, self.end_date)
        out = self.get_ohlcv_by_date(ticker, start_date, end_date)
        if out.empty:
            raise ValueError(f'데이터 없음: {ticker} ({start_date}~{end_date})')
        return out
