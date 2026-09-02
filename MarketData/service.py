from __future__ import annotations

import contextlib
import hashlib
import io
import os
from pathlib import Path

import pandas as pd
import requests

from .naver_index import fetch_naver_index_ohlcv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / "cache" / "MarketData"

_KRX_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
_KRX_REFERER = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
_KRX_HTTP_SESSION: requests.Session | None = None
_PYKRX_STOCK = None
_INDEX_ALIASES = {
    "^KS11": "KOSPI", "KOSPI": "KOSPI", "1001": "KOSPI",
    "^KQ11": "KOSDAQ", "KOSDAQ": "KOSDAQ", "2001": "KOSDAQ",
}


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["open", "high", "low", "close", "volume", "trading_value"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    rename = {
        "시가": "open", "고가": "high", "저가": "low", "종가": "close",
        "거래량": "volume", "거래대금": "trading_value",
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Volume": "volume", "Trading_Value": "trading_value",
        "open": "open", "high": "high", "low": "low", "close": "close",
        "volume": "volume", "trading_value": "trading_value",
    }
    out = df.rename(columns=rename).copy()
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"OHLCV columns missing: {missing}; columns={list(df.columns)}")
    if "trading_value" not in out.columns:
        out["trading_value"] = pd.to_numeric(out["close"], errors="coerce") * pd.to_numeric(out["volume"], errors="coerce")
    for c in columns:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out[columns].dropna(subset=["open", "high", "low", "close"]).copy()


def to_upper_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    return normalize_ohlcv(df).rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume", "trading_value": "Trading_Value"})


def _new_krx_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": _KRX_USER_AGENT, "Referer": _KRX_REFERER, "X-Requested-With": "XMLHttpRequest"})
    try:
        session.get(_KRX_REFERER, timeout=10)
    except requests.RequestException:
        pass
    return session


def reset_krx_http_session() -> requests.Session:
    global _KRX_HTTP_SESSION
    if _KRX_HTTP_SESSION is not None:
        try:
            _KRX_HTTP_SESSION.close()
        except Exception:
            pass
    _KRX_HTTP_SESSION = _new_krx_http_session()
    return _KRX_HTTP_SESSION


def _install_shared_pykrx_transport(webio) -> None:
    reset_krx_http_session()
    def _session_post_read(self, **params):
        session = _KRX_HTTP_SESSION or reset_krx_http_session()
        headers = dict(getattr(self, "headers", {}) or {})
        headers.setdefault("User-Agent", _KRX_USER_AGENT); headers.setdefault("Referer", _KRX_REFERER); headers.setdefault("X-Requested-With", "XMLHttpRequest")
        return session.post(self.url, headers=headers, data=params, timeout=30)
    def _session_get_read(self, **params):
        session = _KRX_HTTP_SESSION or reset_krx_http_session()
        headers = dict(getattr(self, "headers", {}) or {})
        headers.setdefault("User-Agent", _KRX_USER_AGENT); headers.setdefault("Referer", _KRX_REFERER); headers.setdefault("X-Requested-With", "XMLHttpRequest")
        return session.get(self.url, headers=headers, params=params, timeout=30)
    webio.Post.read = _session_post_read
    webio.Get.read = _session_get_read


def load_pykrx_stock():
    global _PYKRX_STOCK
    if _PYKRX_STOCK is not None:
        return _PYKRX_STOCK
    saved_env = {key: os.environ.get(key) for key in ("KRX_ID", "KRX_PW")}
    for key in saved_env:
        os.environ.pop(key, None)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from pykrx import stock
            from pykrx.website.comm import webio
    except ImportError as exc:
        raise RuntimeError("pykrx가 필요합니다. pip install pykrx") from exc
    finally:
        for key, value in saved_env.items():
            if value is not None:
                os.environ[key] = value
    _install_shared_pykrx_transport(webio)
    _PYKRX_STOCK = stock
    return stock


def _yfinance_download(code: str, start: pd.Timestamp, end: pd.Timestamp, market_hint: str | None) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    market = str(market_hint or "").upper()
    candidates = [f"{code}.KQ", f"{code}.KS"] if market == "KOSDAQ" else [f"{code}.KS", f"{code}.KQ"]
    for symbol in candidates:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                raw = yf.download(symbol, start=start.strftime("%Y-%m-%d"), end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), progress=False, auto_adjust=False, threads=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            out = normalize_ohlcv(raw)
            if not out.empty:
                return out
        except Exception:
            continue
    return pd.DataFrame()


class MarketDataService:
    def __init__(self, cache_dir: str | Path = DEFAULT_CACHE_DIR, use_cache: bool = True) -> None:
        self.cache_dir = Path(cache_dir)
        self.ohlcv_cache = self.cache_dir / "ohlcv"; self.index_cache = self.cache_dir / "index"; self.snapshot_cache = self.cache_dir / "snapshot"
        for path in (self.ohlcv_cache, self.index_cache, self.snapshot_cache): path.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self._memory: dict[str, pd.DataFrame] = {}

    @staticmethod
    def normalize_ticker(ticker: str) -> str:
        code = str(ticker or "").strip().upper()
        if code.endswith(".KS") or code.endswith(".KQ"): code = code[:-3]
        return code.zfill(6) if code.isdigit() else code

    @staticmethod
    def _date(value) -> pd.Timestamp:
        return pd.Timestamp(value).normalize()

    def _cache_path(self, root: Path, key: str) -> Path:
        digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
        safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in key.split(":")[0])
        return root / f"{safe}_{digest}.csv"

    def get_ohlcv(self, ticker: str, start, end, *, market_hint: str | None = None, allow_etf: bool = True, fallback_yfinance: bool = True) -> pd.DataFrame:
        raw_code = str(ticker or "").strip().upper()
        if raw_code in _INDEX_ALIASES:
            return self.get_market_index(_INDEX_ALIASES[raw_code], start, end)
        code = self.normalize_ticker(raw_code)
        start_ts = self._date(start); end_ts = min(self._date(end), pd.Timestamp.today().normalize())
        if end_ts < start_ts:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "trading_value"])
        sk, ek = start_ts.strftime("%Y%m%d"), end_ts.strftime("%Y%m%d")
        key = f"{code}:{sk}:{ek}:{str(market_hint or '').upper()}"
        if key in self._memory: return self._memory[key].copy()
        path = self._cache_path(self.ohlcv_cache, key)
        if self.use_cache and path.exists():
            try:
                out = normalize_ohlcv(pd.read_csv(path, index_col=0, parse_dates=True))
                if not out.empty:
                    self._memory[key] = out; return out.copy()
            except Exception: pass
        out = pd.DataFrame()
        try:
            stock = load_pykrx_stock()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): raw = stock.get_market_ohlcv_by_date(sk, ek, code, adjusted=True)
            out = normalize_ohlcv(raw)
            if out.empty and allow_etf:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): raw = stock.get_etf_ohlcv_by_date(sk, ek, code)
                out = normalize_ohlcv(raw)
        except Exception:
            reset_krx_http_session(); out = pd.DataFrame()
        if out.empty and fallback_yfinance: out = _yfinance_download(code, start_ts, end_ts, market_hint)
        if out.empty: raise RuntimeError(f"OHLCV 조회 실패: ticker={code} range={sk}~{ek}")
        if self.use_cache: out.to_csv(path, encoding="utf-8-sig")
        self._memory[key] = out
        return out.copy()

    def get_market_index(self, market: str, start, end) -> pd.DataFrame:
        code = _INDEX_ALIASES.get(str(market or "").strip().upper())
        if not code: raise ValueError(f"지원하지 않는 시장지수: {market}")
        start_ts = self._date(start); end_ts = min(self._date(end), pd.Timestamp.today().normalize())
        sk, ek = start_ts.strftime("%Y%m%d"), end_ts.strftime("%Y%m%d")
        key = f"INDEX_{code}:{sk}:{ek}"
        if key in self._memory: return self._memory[key].copy()
        path = self._cache_path(self.index_cache, key)
        if self.use_cache and path.exists():
            try:
                out = normalize_ohlcv(pd.read_csv(path, index_col=0, parse_dates=True))
                if not out.empty: self._memory[key] = out; return out.copy()
            except Exception: pass
        out = normalize_ohlcv(fetch_naver_index_ohlcv(code, sk, ek))
        if self.use_cache: out.to_csv(path, encoding="utf-8-sig")
        self._memory[key] = out
        return out.copy()

    def resolve_trading_date(self, requested=None, max_lookback_days: int = 30) -> str:
        requested_ts = min(self._date(requested) if requested is not None else pd.Timestamp.today().normalize(), pd.Timestamp.today().normalize())
        start = requested_ts - pd.Timedelta(days=max_lookback_days)
        cal = self.get_ohlcv("005930", start, requested_ts, market_hint="KOSPI", allow_etf=False)
        dates = pd.to_datetime(cal.index, errors="coerce"); dates = dates[(dates.notna()) & (dates.normalize() <= requested_ts)]
        if not len(dates): raise RuntimeError(f"거래일을 찾지 못했습니다: <= {requested_ts.date()}")
        return pd.Timestamp(dates.max()).strftime("%Y%m%d")

    def get_market_return(self, market: str, scan_date: str, lookback_days: int = 10) -> float | None:
        end = self._date(scan_date); start = end - pd.Timedelta(days=max(2, int(lookback_days)))
        try: raw = self.get_market_index(market, start, end)
        except Exception: return None
        close = pd.to_numeric(raw["close"], errors="coerce").dropna()
        if len(close) < 2 or float(close.iloc[-2]) <= 0: return None
        return (float(close.iloc[-1]) / float(close.iloc[-2]) - 1.0) * 100.0

    def get_market_snapshot(self, date: str, market: str, retries: int = 2) -> pd.DataFrame:
        market = str(market).upper()
        if market not in {"KOSPI", "KOSDAQ"}: raise ValueError(f"snapshot market must be KOSPI/KOSDAQ: {market}")
        dt = self._date(date); d = dt.strftime("%Y%m%d"); key = f"{market}:{d}"; path = self._cache_path(self.snapshot_cache, key)
        if self.use_cache and path.exists():
            try:
                cached = pd.read_csv(path, encoding="utf-8-sig", dtype={"ticker": str})
                if not cached.empty:
                    cached["ticker"] = cached["ticker"].astype(str).str.zfill(6); cached["date"] = pd.to_datetime(cached["date"], errors="coerce").dt.normalize(); return cached
            except Exception: pass
        last_exc: Exception | None = None
        for _ in range(max(1, retries)):
            try:
                stock = load_pykrx_stock()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): raw = stock.get_market_ohlcv_by_ticker(d, market=market)
                if raw is None or raw.empty: raise RuntimeError("empty all-ticker snapshot")
                out = raw.rename(columns={"종가": "close", "거래량": "volume", "거래대금": "trading_value", "등락률": "return_pct"}).copy()
                out["ticker"] = [self.normalize_ticker(x) for x in out.index]
                for col in ("close", "volume", "trading_value", "return_pct"):
                    if col not in out.columns: out[col] = pd.NA
                    out[col] = pd.to_numeric(out[col], errors="coerce")
                out["date"] = dt; out["market"] = market
                out = out[["date", "ticker", "market", "close", "volume", "trading_value", "return_pct"]]; out = out[out["ticker"].str.fullmatch(r"\d{6}", na=False)]
                if out.empty: raise RuntimeError("normalized all-ticker snapshot is empty")
                if self.use_cache: out.to_csv(path, index=False, encoding="utf-8-sig")
                return out.reset_index(drop=True)
            except Exception as exc:
                last_exc = exc; reset_krx_http_session()
        raise RuntimeError(f"KRX all-ticker snapshot 실패: {market} {d}: {type(last_exc).__name__}: {last_exc}") from last_exc


_DEFAULT_SERVICE: MarketDataService | None = None

def get_market_data_service() -> MarketDataService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None: _DEFAULT_SERVICE = MarketDataService()
    return _DEFAULT_SERVICE
