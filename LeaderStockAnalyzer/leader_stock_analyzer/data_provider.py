from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import ExcelUniverseService, get_market_data_service  # noqa: E402


class PyKrxLeaderDataProvider:
    """LeaderStock compatibility provider backed by the shared MarketData layer."""

    def __init__(self, cfg: dict, base_dir: str | Path):
        self.cfg = cfg
        self.base_dir = Path(base_dir)
        self.intraday_root = self.base_dir / cfg["data"]["intraday_root"]
        self.market_data = get_market_data_service()
        self.info_excel = Path(
            os.environ.get(
                "LIQUIDITY_UNIVERSE_XLSX",
                str(REPO_ROOT / "KJBChartAnalyzer" / "KOSPI_Info.xlsx"),
            )
        )

    @staticmethod
    def _normalize_daily(df: pd.DataFrame) -> pd.DataFrame:
        columns = ["open", "high", "low", "close", "volume", "trading_value"]
        if df is None or df.empty:
            return pd.DataFrame(columns=columns)
        out = df.rename(
            columns={
                "Open": "open", "High": "high", "Low": "low", "Close": "close",
                "Volume": "volume", "Trading_Value": "trading_value",
                "시가": "open", "고가": "high", "저가": "low", "종가": "close",
                "거래량": "volume", "거래대금": "trading_value",
            }
        ).copy()
        for c in columns:
            if c not in out.columns: out[c] = 0.0
            out[c] = pd.to_numeric(out[c], errors="coerce")
        out.index = pd.to_datetime(out.index, errors="coerce")
        return out[columns].sort_index().dropna(subset=["close"])

    def resolve_scan_date(self, requested: str | None = None) -> str:
        return self.market_data.resolve_trading_date(requested)

    def _excel_frame(self) -> pd.DataFrame:
        service = ExcelUniverseService(self.info_excel)
        infos = service.get_universe(top_n=0, include_etf=False, markets=("KOSPI", "KOSDAQ"))
        meta = pd.DataFrame([
            {"ticker": i.ticker, "name": i.name, "market": i.market, "market_cap": i.market_cap, "excel_trading_value": i.trading_value}
            for i in infos
        ])
        return meta.drop_duplicates("ticker", keep="first")

    def build_universe(self, scan_date: str, top_n: int | None = None) -> pd.DataFrame:
        meta = self._excel_frame()
        try:
            snap = pd.concat([
                self.market_data.get_market_snapshot(scan_date, "KOSPI"),
                self.market_data.get_market_snapshot(scan_date, "KOSDAQ"),
            ], ignore_index=True)
            df = snap.rename(columns={"close": "price"}).copy()
            df = df.merge(meta, on=["ticker", "market"], how="left")
            df["name"] = df["name"].fillna(df["ticker"])
        except Exception as exc:
            print(f"[WARN] Leader snapshot unavailable; using shared Excel universe fallback: {exc}")
            ucfg = self.cfg["universe"]; n = int(top_n or ucfg["top_n"])
            candidates = ExcelUniverseService(self.info_excel).get_universe(
                top_n=max(n * 2, n), sort_by="trading_value", include_etf=False, markets=("KOSPI", "KOSDAQ")
            )
            rows: list[dict] = []
            start = (pd.Timestamp(scan_date) - pd.Timedelta(days=15)).strftime("%Y%m%d")
            for info in candidates:
                try:
                    bars = self.market_data.get_ohlcv(info.ticker, start, scan_date, market_hint=info.market, allow_etf=False)
                    close = pd.to_numeric(bars["close"], errors="coerce").dropna()
                    if close.empty: continue
                    ret = (float(close.iloc[-1]) / float(close.iloc[-2]) - 1.0) * 100.0 if len(close) >= 2 and float(close.iloc[-2]) > 0 else 0.0
                    last = bars.iloc[-1]
                    rows.append({
                        "ticker": info.ticker, "market": info.market, "name": info.name,
                        "price": float(last["close"]), "volume": float(last.get("volume", 0.0) or 0.0),
                        "trading_value": float(info.trading_value or last.get("trading_value", 0.0) or 0.0),
                        "return_pct": ret, "market_cap": info.market_cap,
                    })
                except Exception:
                    continue
            df = pd.DataFrame(rows)
            if df.empty: raise RuntimeError("Leader fallback universe is empty")

        for c in ["price", "volume", "trading_value", "return_pct", "market_cap"]:
            if c not in df.columns: df[c] = pd.NA
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["ticker"] = df["ticker"].astype(str).str.zfill(6); df["name"] = df["name"].fillna(df["ticker"]).astype(str); df["market"] = df["market"].fillna("").astype(str).str.upper()
        ucfg = self.cfg["universe"]
        df = df[(df["price"] >= float(ucfg["min_price"])) & (df["trading_value"].fillna(0) > 0)].copy()
        if ucfg.get("exclude_spac", True): df = df[~df["name"].str.contains("스팩", na=False)].copy()
        if ucfg.get("market_cap_enabled", False) and df["market_cap"].notna().any():
            df = df[(df["market_cap"] >= float(ucfg["market_cap_min"])) & (df["market_cap"] <= float(ucfg["market_cap_max"]))]
        df = df.sort_values(["trading_value", "return_pct"], ascending=[False, False]); n = int(top_n or ucfg["top_n"]); df = df.head(n).copy(); df["trading_value_rank"] = range(1, len(df) + 1)
        return df.set_index("ticker")

    def get_daily(self, ticker: str, scan_date: str, future_days: int = 0) -> pd.DataFrame:
        end_ts = pd.Timestamp(scan_date) + pd.Timedelta(days=max(0, future_days)); start_ts = pd.Timestamp(scan_date) - pd.Timedelta(days=int(self.cfg["data"]["history_days"]))
        return self._normalize_daily(self.market_data.get_ohlcv(ticker, start_ts, end_ts, allow_etf=False))

    def get_market_return(self, market: str, scan_date: str) -> float | None:
        return self.market_data.get_market_return(market, scan_date)

    def get_intraday(self, ticker: str, scan_date: str) -> pd.DataFrame:
        candidates: Iterable[Path] = (
            self.intraday_root / scan_date / f"{str(ticker).zfill(6)}.csv",
            self.intraday_root / f"{scan_date}_{str(ticker).zfill(6)}.csv",
        )
        for path in candidates:
            if not path.exists(): continue
            df = pd.read_csv(path)
            rename = {"datetime": "timestamp", "일시": "timestamp", "시간": "timestamp", "시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume", "거래대금": "trading_value"}
            df = df.rename(columns=rename)
            if "timestamp" in df.columns: df["timestamp"] = pd.to_datetime(df["timestamp"]); df = df.set_index("timestamp")
            required = ["open", "high", "low", "close", "volume"]
            if not all(c in df.columns for c in required): continue
            for c in required + (["trading_value"] if "trading_value" in df.columns else []): df[c] = pd.to_numeric(df[c], errors="coerce")
            if "trading_value" not in df.columns: df["trading_value"] = df["close"] * df["volume"]
            return df.sort_index().dropna(subset=["close"])
        return pd.DataFrame()
