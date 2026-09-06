from __future__ import annotations

import contextlib
import io
from pathlib import Path

import pandas as pd

from .service import (
    MarketDataService,
    get_market_data_service,
    load_pykrx_stock,
    reset_krx_http_session,
)
from .universe import ExcelUniverseService, normalize_ticker

DEFAULT_INFO_XLSX = Path(__file__).resolve().parents[1] / "KJBChartAnalyzer" / "KOSPI_Info.xlsx"


def _price_change_snapshot(date: str, market: str) -> pd.DataFrame:
    """Secondary all-ticker snapshot source used when OHLCV/cap endpoints fail."""
    stock = load_pykrx_stock()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        raw = stock.get_market_price_change_by_ticker(date, date, market=market)
    if raw is None or raw.empty:
        raise RuntimeError("empty price-change snapshot")

    out = raw.rename(
        columns={
            "종목명": "name",
            "종가": "close",
            "거래량": "volume",
            "거래대금": "trading_value",
            "등락률": "return_pct",
        }
    ).copy()
    out["ticker"] = [normalize_ticker(x) for x in out.index]
    if "name" not in out.columns:
        out["name"] = ""
    for col in ("close", "volume", "trading_value", "return_pct"):
        if col not in out.columns:
            out[col] = pd.NA
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["market"] = market
    out = out[out["ticker"].notna()].copy()
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["name"] = out["name"].fillna("").astype(str).str.strip()
    return out[
        ["ticker", "name", "market", "close", "volume", "trading_value", "return_pct"]
    ].reset_index(drop=True)


def _excel_name_map(info_excel: str | Path | None) -> pd.DataFrame:
    if info_excel is None or not Path(info_excel).exists():
        return pd.DataFrame(columns=["ticker", "name"])
    try:
        infos = ExcelUniverseService(info_excel).get_universe(
            top_n=0,
            include_etf=False,
            markets=("KOSPI", "KOSDAQ"),
        )
    except Exception:
        return pd.DataFrame(columns=["ticker", "name"])
    return pd.DataFrame(
        [{"ticker": x.ticker, "name": x.name} for x in infos]
    ).drop_duplicates("ticker", keep="first")


def build_snapshot_universe(
    date: str,
    *,
    top_n: int,
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    info_excel: str | Path | None = DEFAULT_INFO_XLSX,
    service: MarketDataService | None = None,
    require_all_markets: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Build a scan-date liquidity universe from point-in-time market snapshots.

    Primary source is MarketDataService.get_market_snapshot. If the KRX OHLCV
    and market-cap endpoints fail, the KRX price-change endpoint is tried once
    for the same market/date. This avoids silently classifying every Excel row
    as KOSPI and allows KOSDAQ to participate in the daily screen.
    """
    if int(top_n) <= 0:
        raise ValueError("top_n must be positive")

    normalized = tuple(dict.fromkeys(str(x).upper() for x in markets if str(x).strip()))
    invalid = [x for x in normalized if x not in {"KOSPI", "KOSDAQ"}]
    if invalid or not normalized:
        raise ValueError(f"unsupported markets: {invalid or normalized}")

    svc = service or get_market_data_service()
    d = pd.Timestamp(date).normalize().strftime("%Y%m%d")
    frames: list[pd.DataFrame] = []
    loaded: list[str] = []
    failed: dict[str, str] = {}

    for market in normalized:
        try:
            snap = svc.get_market_snapshot(d, market, retries=1).copy()
            if snap.empty:
                raise RuntimeError("empty market snapshot")
            if "name" not in snap.columns:
                snap["name"] = ""
            keep = ["ticker", "name", "market", "close", "volume", "trading_value"]
            for col in keep:
                if col not in snap.columns:
                    snap[col] = pd.NA
            frames.append(snap[keep].copy())
            loaded.append(market)
            continue
        except Exception as primary_exc:
            reset_krx_http_session()
            try:
                frames.append(
                    _price_change_snapshot(d, market)[
                        ["ticker", "name", "market", "close", "volume", "trading_value"]
                    ]
                )
                loaded.append(market)
                print(
                    f"[WARN] {market} universe snapshot used KRX price-change fallback: "
                    f"{type(primary_exc).__name__}: {primary_exc}"
                )
                continue
            except Exception as secondary_exc:
                failed[market] = (
                    f"snapshot={type(primary_exc).__name__}: {primary_exc}; "
                    f"price_change={type(secondary_exc).__name__}: {secondary_exc}"
                )

    if require_all_markets and failed:
        details = " | ".join(f"{k}: {v}" for k, v in failed.items())
        raise RuntimeError(f"point-in-time universe missing market(s): {details}")
    if not frames:
        raise RuntimeError(f"no point-in-time universe data for {d}")

    out = pd.concat(frames, ignore_index=True)
    out["ticker"] = out["ticker"].map(normalize_ticker)
    out = out[out["ticker"].notna()].copy()
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["market"] = out["market"].astype(str).str.upper()
    for col in ("close", "volume", "trading_value"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["trading_value"] = out["trading_value"].where(
        out["trading_value"].fillna(0).gt(0),
        out["close"].fillna(0) * out["volume"].fillna(0),
    )
    out = out[
        out["close"].fillna(0).gt(0) & out["trading_value"].fillna(0).gt(0)
    ].copy()

    names = _excel_name_map(info_excel)
    if not names.empty:
        out = out.merge(names, on="ticker", how="left", suffixes=("", "_excel"))
        out["name"] = out["name"].where(
            out["name"].fillna("").astype(str).str.strip().ne(""),
            out["name_excel"],
        )
        out = out.drop(columns=["name_excel"])
    out["name"] = out["name"].fillna("").astype(str).str.strip()
    out["name"] = out["name"].where(out["name"].ne(""), out["ticker"])

    out = (
        out.drop_duplicates(["ticker"], keep="first")
        .sort_values(["trading_value", "ticker"], ascending=[False, True])
        .head(int(top_n))
        .reset_index(drop=True)
    )
    out["source_rank"] = range(1, len(out) + 1)
    return out[
        ["source_rank", "ticker", "name", "market", "close", "volume", "trading_value"]
    ], {
        "source_mode": "POINT_IN_TIME_ALL_MARKET_SNAPSHOT",
        "membership_mode": "POINT_IN_TIME_SNAPSHOT",
        "markets_loaded": loaded,
        "markets_failed": failed,
        "row_count": int(len(out)),
    }
