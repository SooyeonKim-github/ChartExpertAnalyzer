from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


class PyKrxLeaderDataProvider:
    def __init__(self, cfg: dict, base_dir: str | Path):
        self.cfg = cfg
        self.base_dir = Path(base_dir)
        self.cache_dir = self.base_dir / cfg["data"]["cache_root"]
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.intraday_root = self.base_dir / cfg["data"]["intraday_root"]

    @staticmethod
    def _stock():
        try:
            from pykrx import stock
        except ImportError as exc:
            raise RuntimeError("pykrx is not installed. Run: pip install -r requirements.txt") from exc
        return stock

    @staticmethod
    def _normalize_daily(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "trading_value"])
        out = df.rename(columns={
            "시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume", "거래대금": "trading_value",
            "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume",
        }).copy()
        for c in ["open", "high", "low", "close", "volume", "trading_value"]:
            if c not in out.columns:
                out[c] = 0.0
            out[c] = pd.to_numeric(out[c], errors="coerce")
        out.index = pd.to_datetime(out.index)
        return out[["open", "high", "low", "close", "volume", "trading_value"]].sort_index().dropna(subset=["close"])

    def resolve_scan_date(self, requested: str | None = None) -> str:
        stock = self._stock()
        ts = pd.Timestamp(requested) if requested else pd.Timestamp.today()
        ts = ts.normalize()
        for offset in range(0, 15):
            d = (ts - pd.Timedelta(days=offset)).strftime("%Y%m%d")
            try:
                snap = stock.get_market_ohlcv_by_ticker(d, market="ALL")
                if snap is not None and not snap.empty:
                    return d
            except Exception:
                continue
        raise RuntimeError(f"Could not resolve a market date near {ts.date()}")

    def build_universe(self, scan_date: str, top_n: int | None = None) -> pd.DataFrame:
        stock = self._stock()
        snap = stock.get_market_ohlcv_by_ticker(scan_date, market="ALL")
        if snap is None or snap.empty:
            raise RuntimeError(f"No market snapshot for {scan_date}")
        df = snap.rename(columns={"종가": "price", "거래량": "volume", "거래대금": "trading_value", "등락률": "return_pct"}).copy()
        for c in ["price", "volume", "trading_value", "return_pct"]:
            if c not in df.columns:
                df[c] = 0.0
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        df.index = df.index.astype(str).str.zfill(6)
        kospi = set(stock.get_market_ticker_list(scan_date, market="KOSPI"))
        kosdaq = set(stock.get_market_ticker_list(scan_date, market="KOSDAQ"))
        df["market"] = ["KOSPI" if t in kospi else "KOSDAQ" if t in kosdaq else "OTHER" for t in df.index]
        df = df[df["market"].isin(["KOSPI", "KOSDAQ"])].copy()
        df["name"] = [stock.get_market_ticker_name(t) for t in df.index]

        try:
            cap = stock.get_market_cap_by_ticker(scan_date, market="ALL")
            if cap is not None and not cap.empty and "시가총액" in cap.columns:
                cap_s = pd.to_numeric(cap["시가총액"], errors="coerce")
                cap_s.index = cap_s.index.astype(str).str.zfill(6)
                df["market_cap"] = cap_s.reindex(df.index)
            else:
                df["market_cap"] = None
        except Exception:
            df["market_cap"] = None

        ucfg = self.cfg["universe"]
        df = df[(df["price"] >= float(ucfg["min_price"])) & (df["trading_value"] > 0)].copy()
        if ucfg.get("exclude_spac", True):
            df = df[~df["name"].str.contains("스팩", na=False)].copy()
        if ucfg.get("market_cap_enabled", False) and df["market_cap"].notna().any():
            df = df[(df["market_cap"] >= float(ucfg["market_cap_min"])) & (df["market_cap"] <= float(ucfg["market_cap_max"]))]
        df = df.sort_values(["trading_value", "return_pct"], ascending=[False, False])
        n = int(top_n or ucfg["top_n"])
        df = df.head(n).copy()
        df["trading_value_rank"] = range(1, len(df) + 1)
        df.index.name = "ticker"
        return df

    def get_daily(self, ticker: str, scan_date: str, future_days: int = 0) -> pd.DataFrame:
        stock = self._stock()
        end_ts = pd.Timestamp(scan_date) + pd.Timedelta(days=max(0, future_days))
        start_ts = pd.Timestamp(scan_date) - pd.Timedelta(days=int(self.cfg["data"]["history_days"]))
        sk, ek = start_ts.strftime("%Y%m%d"), end_ts.strftime("%Y%m%d")
        path = self.cache_dir / f"daily_{ticker}_{sk}_{ek}.csv"
        if path.exists():
            return self._normalize_daily(pd.read_csv(path, index_col=0, parse_dates=True))
        raw = stock.get_market_ohlcv_by_date(sk, ek, str(ticker).zfill(6), adjusted=True)
        out = self._normalize_daily(raw)
        if not out.empty:
            out.to_csv(path, encoding="utf-8-sig")
        return out

    def get_market_return(self, market: str, scan_date: str) -> float | None:
        stock = self._stock()
        code = "1001" if market == "KOSPI" else "2001"
        start = (pd.Timestamp(scan_date) - pd.Timedelta(days=10)).strftime("%Y%m%d")
        try:
            raw = stock.get_index_ohlcv_by_date(start, scan_date, code)
        except Exception:
            return None
        if raw is None or raw.empty or "종가" not in raw.columns or len(raw) < 2:
            return None
        close = pd.to_numeric(raw["종가"], errors="coerce").dropna()
        if len(close) < 2 or float(close.iloc[-2]) <= 0:
            return None
        return (float(close.iloc[-1]) / float(close.iloc[-2]) - 1.0) * 100.0

    def get_intraday(self, ticker: str, scan_date: str) -> pd.DataFrame:
        candidates: Iterable[Path] = (
            self.intraday_root / scan_date / f"{str(ticker).zfill(6)}.csv",
            self.intraday_root / f"{scan_date}_{str(ticker).zfill(6)}.csv",
        )
        for path in candidates:
            if not path.exists():
                continue
            df = pd.read_csv(path)
            rename = {"datetime": "timestamp", "일시": "timestamp", "시간": "timestamp", "시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume", "거래대금": "trading_value"}
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
