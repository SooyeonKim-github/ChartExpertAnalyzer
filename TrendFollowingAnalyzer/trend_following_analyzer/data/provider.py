from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import ExcelUniverseService, get_market_data_service  # noqa: E402


class TrendFollowingDataProvider:
    """Market-data adapter for TrendFollowingAnalyzer.

    Strategy logic stays inside TrendFollowingAnalyzer while raw OHLCV,
    universe, and index retrieval reuse the repository-wide MarketData service.
    """

    def __init__(
        self,
        cfg: dict,
        base_dir: str | Path,
        universe_xlsx: str | Path | None = None,
    ) -> None:
        self.cfg = cfg
        self.base_dir = Path(base_dir)
        self.market_data = get_market_data_service()
        self.universe_xlsx = self._resolve_universe_xlsx(universe_xlsx)
        self._history_cache: dict[str, pd.DataFrame] = {}
        self._index_cache: dict[str, pd.DataFrame] = {}
        self._candidate_infos: list = []
        self._candidate_top_n: int | None = None

    def _resolve_universe_xlsx(self, explicit: str | Path | None) -> Path:
        candidates: list[Path] = []
        if explicit:
            candidates.append(Path(explicit))

        env_path = os.environ.get("LIQUIDITY_UNIVERSE_XLSX", "").strip()
        if env_path:
            candidates.append(Path(env_path))

        candidates.extend(
            [
                self.base_dir / "KOSPI_Info.xlsx",
                REPO_ROOT / "KJBChartAnalyzer" / "KOSPI_Info.xlsx",
            ]
        )

        for path in candidates:
            if path.exists():
                return path

        tried = "\n".join(f"- {p}" for p in candidates)
        raise FileNotFoundError(
            "Universe Excel not found. Use --universe-xlsx or LIQUIDITY_UNIVERSE_XLSX.\n"
            f"Tried:\n{tried}"
        )

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

        for col in columns:
            if col not in out.columns:
                out[col] = 0.0
            out[col] = pd.to_numeric(out[col], errors="coerce")

        out.index = pd.to_datetime(out.index, errors="coerce")
        out = out[~out.index.isna()]
        out = out[~out.index.duplicated(keep="last")].sort_index()
        return out[columns].dropna(subset=["close"])

    def resolve_scan_date(self, requested: str | None = None) -> str:
        return self.market_data.resolve_trading_date(requested)

    def _candidate_pool_size(self, top_n: int) -> int:
        multiplier = max(1, int(self.cfg["universe"].get("candidate_multiplier", 3)))
        return max(int(top_n), int(top_n) * multiplier)

    def _load_candidate_infos(self, top_n: int) -> list:
        if self._candidate_infos and self._candidate_top_n == top_n:
            return self._candidate_infos

        service = ExcelUniverseService(self.universe_xlsx)
        self._candidate_infos = service.get_universe(
            top_n=self._candidate_pool_size(top_n),
            sort_by="trading_value",
            include_etf=False,
            markets=("KOSPI", "KOSDAQ"),
        )
        self._candidate_top_n = top_n
        return self._candidate_infos

    def _load_history(self, info, scan_date: str) -> pd.DataFrame:
        ticker = str(info.ticker).zfill(6)
        if ticker in self._history_cache:
            return self._history_cache[ticker]

        history_days = int(self.cfg["data"].get("history_days", 520))
        end = pd.Timestamp(scan_date).normalize()
        start = end - pd.Timedelta(days=history_days)

        bars = self.market_data.get_ohlcv(
            ticker,
            start,
            end,
            market_hint=info.market,
            allow_etf=False,
        )
        bars = self._normalize_daily(bars)
        self._history_cache[ticker] = bars
        return bars

    def build_universe(self, scan_date: str, top_n: int | None = None) -> pd.DataFrame:
        ucfg = self.cfg["universe"]
        n = int(top_n or ucfg.get("top_n", 100))
        target = pd.Timestamp(scan_date).normalize()
        rows: list[dict] = []

        for info in self._load_candidate_infos(n):
            try:
                bars = self._load_history(info, scan_date)
                hist = bars[bars.index.normalize() <= target]
                if hist.empty or pd.Timestamp(hist.index[-1]).normalize() != target:
                    continue

                last = hist.iloc[-1]
                close = float(last["close"])
                volume = float(last.get("volume", 0.0) or 0.0)
                trading_value = float(last.get("trading_value", 0.0) or 0.0)
                if trading_value <= 0 and close > 0 and volume > 0:
                    trading_value = close * volume

                rows.append(
                    {
                        "ticker": str(info.ticker).zfill(6),
                        "name": str(info.name),
                        "market": str(info.market).upper(),
                        "close": close,
                        "trading_value": trading_value,
                    }
                )
            except Exception:
                continue

        df = pd.DataFrame(rows)
        if df.empty:
            raise RuntimeError(f"Trend-following universe is empty for {scan_date}")

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["trading_value"] = pd.to_numeric(df["trading_value"], errors="coerce")
        df = df[
            (df["close"] >= float(ucfg.get("min_price", 0)))
            & (df["trading_value"].fillna(0) > 0)
        ].copy()

        if ucfg.get("exclude_spac", True):
            df = df[~df["name"].str.contains("스팩", na=False)].copy()

        df = df.sort_values("trading_value", ascending=False).head(n).copy()
        df["trading_value_rank"] = range(1, len(df) + 1)
        return df.set_index("ticker")

    def get_daily(self, ticker: str, scan_date: str) -> pd.DataFrame:
        code = str(ticker).zfill(6)
        cached = self._history_cache.get(code)
        if cached is not None:
            target = pd.Timestamp(scan_date).normalize()
            return cached[cached.index.normalize() <= target].copy()

        history_days = int(self.cfg["data"].get("history_days", 520))
        end = pd.Timestamp(scan_date).normalize()
        start = end - pd.Timedelta(days=history_days)
        return self._normalize_daily(
            self.market_data.get_ohlcv(code, start, end, allow_etf=False)
        )

    def get_market_index(self, market: str, scan_date: str) -> pd.DataFrame:
        """Load enough KOSPI/KOSDAQ index history for MA150 regime classification."""
        market_key = str(market).upper()
        if market_key in self._index_cache:
            return self._index_cache[market_key].copy()

        history_days = max(
            int(self.cfg["data"].get("history_days", 520)),
            int(self.cfg.get("market_regime", {}).get("history_days", 520)),
        )
        end = pd.Timestamp(scan_date).normalize()
        start = end - pd.Timedelta(days=history_days)
        raw = self.market_data.get_market_index(market_key, start, end)
        out = self._normalize_daily(raw)
        out = out[out.index.normalize() <= end].copy()
        self._index_cache[market_key] = out
        return out.copy()
