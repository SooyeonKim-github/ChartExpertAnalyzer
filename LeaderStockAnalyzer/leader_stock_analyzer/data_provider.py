from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import ExcelUniverseService, get_market_data_service  # noqa: E402
from MarketData.service import load_pykrx_stock  # noqa: E402


class PyKrxLeaderDataProvider:
    """LeaderStock adapter over the shared MarketData layer.

    Leader range analysis intentionally follows the same market-data pattern as
    KJB/Swing: build a stable Excel candidate pool, load each ticker's OHLCV,
    then rank the candidates by the *scan-date* trading value.  It does not use
    pykrx's fragile all-ticker snapshot endpoints.
    """

    def __init__(self, cfg: dict, base_dir: str | Path):
        self.cfg = cfg
        self.base_dir = Path(base_dir)
        self.intraday_root = self.base_dir / cfg["data"]["intraday_root"]
        self.cache_root = self.base_dir / cfg["data"].get("cache_root", "cache")
        self.sector_cache_root = self.cache_root / "sectors"
        self.sector_cache_root.mkdir(parents=True, exist_ok=True)
        self.market_data = get_market_data_service()
        self.info_excel = Path(
            os.environ.get(
                "LIQUIDITY_UNIVERSE_XLSX",
                str(REPO_ROOT / "KJBChartAnalyzer" / "KOSPI_Info.xlsx"),
            )
        )
        self._candidate_infos: list = []
        self._candidate_top_n: int | None = None
        self._range_price_cache: dict[str, pd.DataFrame] = {}
        self._range_cache_start: pd.Timestamp | None = None
        self._range_cache_end: pd.Timestamp | None = None

    @staticmethod
    def _normalize_daily(df: pd.DataFrame) -> pd.DataFrame:
        columns = ["open", "high", "low", "close", "volume", "trading_value"]
        if df is None or df.empty:
            return pd.DataFrame(columns=columns)
        out = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
                "Trading_Value": "trading_value",
                "시가": "open",
                "고가": "high",
                "저가": "low",
                "종가": "close",
                "거래량": "volume",
                "거래대금": "trading_value",
            }
        ).copy()
        for c in columns:
            if c not in out.columns:
                out[c] = 0.0
            out[c] = pd.to_numeric(out[c], errors="coerce")
        out.index = pd.to_datetime(out.index, errors="coerce")
        out = out[~out.index.isna()]
        out = out[~out.index.duplicated(keep="last")].sort_index()
        return out[columns].dropna(subset=["close"])

    def _candidate_pool_size(self, top_n: int) -> int:
        multiplier = max(1, int(self.cfg.get("universe", {}).get("candidate_multiplier", 3)))
        return max(int(top_n), int(top_n) * multiplier)

    def _load_candidate_infos(self, top_n: int) -> list:
        n = int(top_n)
        if self._candidate_infos and self._candidate_top_n == n:
            return self._candidate_infos
        service = ExcelUniverseService(self.info_excel)
        self._candidate_infos = service.get_universe(
            top_n=self._candidate_pool_size(n),
            sort_by="trading_value",
            include_etf=False,
            markets=("KOSPI", "KOSDAQ"),
        )
        self._candidate_top_n = n
        return self._candidate_infos

    def prepare_range(self, start_date: str, end_date: str, top_n: int | None = None) -> None:
        """Preload candidate OHLCV once for range scans.

        This mirrors KJB/Swing range execution and prevents one network request
        per ticker per scan date.  The loaded history also supplies Leader
        signals, so subsequent screen_date calls reuse the same frames.
        """
        ucfg = self.cfg["universe"]
        n = int(top_n or ucfg["top_n"])
        candidates = self._load_candidate_infos(n)
        history_days = int(self.cfg["data"].get("history_days", 420))
        fetch_start = pd.Timestamp(start_date).normalize() - pd.Timedelta(days=history_days + 30)
        fetch_end = pd.Timestamp(end_date).normalize()

        self._range_price_cache = {}
        self._range_cache_start = fetch_start
        self._range_cache_end = fetch_end

        print(
            f"[INFO] Leader market-data preload | candidate_pool={len(candidates)} "
            f"| target_top_n={n} | {fetch_start:%Y-%m-%d}~{fetch_end:%Y-%m-%d}"
        )
        failed = 0
        for idx, info in enumerate(candidates, start=1):
            try:
                bars = self.market_data.get_ohlcv(
                    info.ticker,
                    fetch_start,
                    fetch_end,
                    market_hint=info.market,
                    allow_etf=False,
                )
                bars = self._normalize_daily(bars)
                if bars.empty:
                    raise RuntimeError("empty OHLCV")
                self._range_price_cache[str(info.ticker).zfill(6)] = bars
            except Exception:
                failed += 1
            if idx == len(candidates) or idx % 25 == 0:
                print(
                    f"[INFO] Leader preload {idx}/{len(candidates)} "
                    f"| loaded={len(self._range_price_cache)} | failed={failed}"
                )

        if not self._range_price_cache:
            raise RuntimeError("Leader range market-data preload returned no OHLCV")

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        start = pd.Timestamp(start_date).normalize()
        end = pd.Timestamp(end_date).normalize()
        try:
            index_df = self.market_data.get_market_index("KOSPI", start, end)
            dates = pd.to_datetime(index_df.index, errors="coerce")
            dates = dates[(dates.notna()) & (dates.normalize() >= start) & (dates.normalize() <= end)]
            if len(dates):
                return sorted({pd.Timestamp(x).strftime("%Y%m%d") for x in dates})
        except Exception:
            pass

        try:
            samsung = self.market_data.get_ohlcv(
                "005930", start, end, market_hint="KOSPI", allow_etf=False
            )
            dates = pd.to_datetime(samsung.index, errors="coerce")
            dates = dates[(dates.notna()) & (dates.normalize() >= start) & (dates.normalize() <= end)]
            if len(dates):
                return sorted({pd.Timestamp(x).strftime("%Y%m%d") for x in dates})
        except Exception:
            pass

        cached_dates: set[str] = set()
        for bars in self._range_price_cache.values():
            idx = pd.to_datetime(bars.index, errors="coerce")
            for dt in idx:
                if pd.isna(dt):
                    continue
                ts = pd.Timestamp(dt).normalize()
                if start <= ts <= end:
                    cached_dates.add(ts.strftime("%Y%m%d"))
        if cached_dates:
            return sorted(cached_dates)
        raise RuntimeError(f"Could not resolve trading dates: {start_date}~{end_date}")

    def resolve_scan_date(self, requested: str | None = None) -> str:
        if requested is not None and self._range_cache_start is not None and self._range_cache_end is not None:
            target = pd.Timestamp(requested).normalize()
            if self._range_cache_start <= target <= self._range_cache_end:
                return target.strftime("%Y%m%d")
        return self.market_data.resolve_trading_date(requested)

    def _bars_for_candidate(self, info, scan_date: str) -> pd.DataFrame:
        ticker = str(info.ticker).zfill(6)
        cached = self._range_price_cache.get(ticker)
        if cached is not None and not cached.empty:
            return cached
        start = pd.Timestamp(scan_date).normalize() - pd.Timedelta(days=30)
        bars = self.market_data.get_ohlcv(
            ticker,
            start,
            scan_date,
            market_hint=info.market,
            allow_etf=False,
        )
        return self._normalize_daily(bars)

    def build_universe(self, scan_date: str, top_n: int | None = None) -> pd.DataFrame:
        ucfg = self.cfg["universe"]
        n = int(top_n or ucfg["top_n"])
        candidates = self._load_candidate_infos(n)
        target = pd.Timestamp(scan_date).normalize()
        rows: list[dict] = []

        for info in candidates:
            try:
                bars = self._bars_for_candidate(info, scan_date)
                hist = bars[pd.to_datetime(bars.index).normalize() <= target]
                if hist.empty:
                    continue
                last_date = pd.Timestamp(hist.index[-1]).normalize()
                if last_date != target:
                    continue
                close = pd.to_numeric(hist["close"], errors="coerce").dropna()
                if close.empty:
                    continue
                last = hist.iloc[-1]
                price = float(last["close"])
                volume = float(last.get("volume", 0.0) or 0.0)
                trading_value = float(last.get("trading_value", 0.0) or 0.0)
                if trading_value <= 0 and price > 0 and volume > 0:
                    trading_value = price * volume
                ret = (
                    (float(close.iloc[-1]) / float(close.iloc[-2]) - 1.0) * 100.0
                    if len(close) >= 2 and float(close.iloc[-2]) > 0
                    else 0.0
                )
                rows.append(
                    {
                        "ticker": str(info.ticker).zfill(6),
                        "market": str(info.market).upper(),
                        "name": info.name,
                        "price": price,
                        "volume": volume,
                        "trading_value": trading_value,
                        "return_pct": ret,
                        "market_cap": info.market_cap,
                    }
                )
            except Exception:
                continue

        df = pd.DataFrame(rows)
        if df.empty:
            raise RuntimeError(f"Leader universe is empty for {scan_date}")

        for c in ["price", "volume", "trading_value", "return_pct", "market_cap"]:
            if c not in df.columns:
                df[c] = pd.NA
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
        df["name"] = df["name"].fillna(df["ticker"]).astype(str)
        df["market"] = df["market"].fillna("").astype(str).str.upper()
        df = df[
            (df["price"] >= float(ucfg["min_price"]))
            & (df["trading_value"].fillna(0) > 0)
        ].copy()
        if ucfg.get("exclude_spac", True):
            df = df[~df["name"].str.contains("스팩", na=False)].copy()
        if ucfg.get("market_cap_enabled", False) and df["market_cap"].notna().any():
            df = df[
                (df["market_cap"] >= float(ucfg["market_cap_min"]))
                & (df["market_cap"] <= float(ucfg["market_cap_max"]))
            ]

        df = df.sort_values(
            ["trading_value", "return_pct"],
            ascending=[False, False],
            na_position="last",
        ).head(n).copy()
        df["trading_value_rank"] = range(1, len(df) + 1)
        return df.set_index("ticker")

    def get_daily(self, ticker: str, scan_date: str, future_days: int = 0) -> pd.DataFrame:
        end_ts = pd.Timestamp(scan_date).normalize() + pd.Timedelta(days=max(0, future_days))
        start_ts = pd.Timestamp(scan_date).normalize() - pd.Timedelta(
            days=int(self.cfg["data"]["history_days"])
        )
        code = str(ticker).zfill(6)
        cached = self._range_price_cache.get(code)
        if (
            cached is not None
            and self._range_cache_start is not None
            and self._range_cache_end is not None
            and start_ts >= self._range_cache_start
            and end_ts <= self._range_cache_end
        ):
            out = cached[(cached.index >= start_ts) & (cached.index <= end_ts)].copy()
            if not out.empty:
                return out
        return self._normalize_daily(
            self.market_data.get_ohlcv(ticker, start_ts, end_ts, allow_etf=False)
        )

    def get_market_return(self, market: str, scan_date: str) -> float | None:
        return self.market_data.get_market_return(market, scan_date)

    def get_market_period_return(self, market: str, scan_date: str, bars: int) -> float | None:
        end = pd.Timestamp(scan_date)
        start = end - pd.Timedelta(days=max(30, int(bars) * 3))
        try:
            df = self.market_data.get_market_index(market, start, end)
        except Exception:
            return None
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(close) <= bars or float(close.iloc[-bars - 1]) <= 0:
            return None
        return (float(close.iloc[-1]) / float(close.iloc[-bars - 1]) - 1.0) * 100.0

    def get_sector_map(self, scan_date: str) -> dict[str, str]:
        """Return point-in-time KRX sector membership and cache it by scan date."""
        cache_path = self.sector_cache_root / f"{scan_date}.csv"
        if cache_path.exists():
            try:
                cached = pd.read_csv(
                    cache_path,
                    encoding="utf-8-sig",
                    dtype={"ticker": str},
                )
                if {"ticker", "sector"}.issubset(cached.columns):
                    cached["ticker"] = cached["ticker"].astype(str).str.zfill(6)
                    return dict(zip(cached["ticker"], cached["sector"].astype(str)))
            except Exception:
                pass

        rows: list[dict[str, str]] = []
        try:
            stock = load_pykrx_stock()
            for market in ("KOSPI", "KOSDAQ"):
                try:
                    with contextlib.redirect_stdout(None), contextlib.redirect_stderr(None):
                        raw = stock.get_market_sector_classifications(scan_date, market)
                except Exception:
                    raw = pd.DataFrame()
                if raw is None or raw.empty or "업종명" not in raw.columns:
                    continue
                for ticker, row in raw.iterrows():
                    code = str(ticker).zfill(6)
                    sector = str(row.get("업종명", "")).strip()
                    if code.isdigit() and len(code) == 6 and sector:
                        rows.append({"ticker": code, "market": market, "sector": sector})
        except Exception:
            rows = []

        if not rows:
            return {}
        df = pd.DataFrame(rows).drop_duplicates("ticker", keep="last")
        try:
            df.to_csv(cache_path, index=False, encoding="utf-8-sig")
        except Exception:
            pass
        return dict(zip(df["ticker"], df["sector"]))

    def get_intraday(self, ticker: str, scan_date: str) -> pd.DataFrame:
        candidates: Iterable[Path] = (
            self.intraday_root / scan_date / f"{str(ticker).zfill(6)}.csv",
            self.intraday_root / f"{scan_date}_{str(ticker).zfill(6)}.csv",
        )
        for path in candidates:
            if not path.exists():
                continue
            df = pd.read_csv(path)
            rename = {
                "datetime": "timestamp",
                "일시": "timestamp",
                "시간": "timestamp",
                "시가": "open",
                "고가": "high",
                "저가": "low",
                "종가": "close",
                "거래량": "volume",
                "거래대금": "trading_value",
            }
            df = df.rename(columns=rename)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.set_index("timestamp")
            required = ["open", "high", "low", "close", "volume"]
            if not all(c in df.columns for c in required):
                continue
            for c in required + (["trading_value"] if "trading_value" in df.columns else []):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            if "trading_value" not in df.columns:
                df["trading_value"] = df["close"] * df["volume"]
            return df.sort_index().dropna(subset=["close"])
        return pd.DataFrame()
