from __future__ import annotations

from pathlib import Path

import pandas as pd

from .service import MarketDataService, get_market_data_service
from .universe import ExcelUniverseService

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INFO_XLSX = ROOT / "KJBChartAnalyzer" / "KOSPI_Info.xlsx"


def _rank_raw_liquidity(
    raw: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    top_n: int,
    lookback: int,
) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise RuntimeError("거래대금 원천 데이터가 비어 있습니다.")

    x = raw.copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["ticker"] = x["ticker"].astype(str).str.zfill(6)
    x["trading_value"] = pd.to_numeric(x["trading_value"], errors="coerce").fillna(0.0)
    x["volume"] = pd.to_numeric(x.get("volume"), errors="coerce")
    x["close"] = pd.to_numeric(x.get("close"), errors="coerce")
    x = x.dropna(subset=["date"]).drop_duplicates(["date", "ticker"], keep="last").sort_values(["ticker", "date"]).reset_index(drop=True)
    x["avg_trading_value_20d"] = x.groupby("ticker", group_keys=False)["trading_value"].rolling(window=int(lookback), min_periods=int(lookback)).mean().reset_index(level=0, drop=True)

    if start == end:
        available = sorted(x.loc[x["date"] <= end, "date"].dropna().unique())
        if not available:
            raise RuntimeError("기준일 이전의 거래일을 찾지 못했습니다.")
        target_dates = [pd.Timestamp(available[-1]).normalize()]
    else:
        target_dates = [pd.Timestamp(d).normalize() for d in sorted(x.loc[(x["date"] >= start) & (x["date"] <= end), "date"].dropna().unique())]

    selected: list[pd.DataFrame] = []
    for idx, date in enumerate(target_dates, start=1):
        day = x[x["date"].eq(date)].copy()
        day = day[day["avg_trading_value_20d"].notna() & day["avg_trading_value_20d"].gt(0)]
        day = day.sort_values(["avg_trading_value_20d", "trading_value", "ticker"], ascending=[False, False, True]).head(int(top_n))
        if day.empty:
            continue
        day = day.reset_index(drop=True)
        day["source_rank"] = range(1, len(day) + 1)
        day["universe_cutoff_value"] = float(day["avg_trading_value_20d"].iloc[-1])
        day["lookback_days"] = int(lookback)
        selected.append(day)
        if idx == 1 or idx == len(target_dates) or idx % 100 == 0:
            print(f"[LIQUIDITY] rank date {idx}/{len(target_dates)} {date:%Y-%m-%d} selected={len(day)}")

    if not selected:
        raise RuntimeError(f"최근 {lookback}거래일 평균 거래대금 Universe를 만들지 못했습니다.")

    out = pd.concat(selected, ignore_index=True)
    for col, default in (("name", ""), ("market", "")):
        if col not in out.columns:
            out[col] = default
    return out[["date", "source_rank", "ticker", "name", "market", "trading_value", "avg_trading_value_20d", "universe_cutoff_value", "lookback_days", "volume", "close"]].sort_values(["date", "source_rank"]).reset_index(drop=True)


def _load_name_map(info_excel: str | Path, markets: tuple[str, ...]) -> pd.DataFrame:
    infos = ExcelUniverseService(info_excel).get_universe(top_n=0, include_etf=False, markets=markets)
    return pd.DataFrame([{"ticker": i.ticker, "name": i.name, "market": i.market} for i in infos]).drop_duplicates("ticker", keep="first")


def _merge_names(raw: pd.DataFrame, name_map: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw
    out = raw.copy()
    if "name" in out.columns:
        out = out.drop(columns="name")
    if "market" in out.columns:
        out = out.merge(name_map[["ticker", "name"]].drop_duplicates("ticker", keep="first"), on="ticker", how="left")
    else:
        out = out.merge(name_map, on="ticker", how="left")
    out["name"] = out["name"].fillna(out["ticker"])
    return out


def _snapshot_path(service: MarketDataService, start: pd.Timestamp, end: pd.Timestamp, top_n: int, lookback: int, markets: tuple[str, ...], info_excel: str | Path) -> pd.DataFrame:
    warm_start = start - pd.Timedelta(days=max(120, int(lookback) * 8))
    calendar = service.get_ohlcv("005930", warm_start, end, market_hint="KOSPI", allow_etf=False)
    target_dates = [pd.Timestamp(d).normalize() for d in calendar.index if pd.Timestamp(d).normalize() <= end and pd.Timestamp(d).normalize() >= warm_start]
    if not target_dates:
        raise RuntimeError("거래일 캘린더가 비어 있습니다.")
    frames: list[pd.DataFrame] = []
    total = len(target_dates)
    for idx, date in enumerate(target_dates, start=1):
        day = pd.concat([service.get_market_snapshot(date.strftime("%Y%m%d"), market) for market in markets], ignore_index=True)
        frames.append(day)
        if idx == 1 or idx == total or idx % 20 == 0:
            print(f"[LIQUIDITY] snapshot {idx}/{total} {date:%Y-%m-%d} rows={len(day)}")
    raw = _merge_names(pd.concat(frames, ignore_index=True), _load_name_map(info_excel, markets))
    return _rank_raw_liquidity(raw, start, end, top_n, lookback)


def _per_ticker_fallback(service: MarketDataService, start: pd.Timestamp, end: pd.Timestamp, top_n: int, lookback: int, markets: tuple[str, ...], info_excel: str | Path) -> pd.DataFrame:
    infos = ExcelUniverseService(info_excel).get_universe(top_n=0, include_etf=False, markets=markets)
    history_start = start - pd.Timedelta(days=max(120, int(lookback) * 8))
    actual_end = min(end, pd.Timestamp.today().normalize())
    print("[FALLBACK] KRX all-ticker snapshot unavailable -> per-ticker OHLCV mode.")
    print(f"[FALLBACK] Candidate list: {Path(info_excel)}")
    print(f"[FALLBACK] Candidate tickers: {len(infos):,}")
    print("[INFO] Ranking remains date-wise recent trading-value average (point-in-time values).")
    print("[INFO] Candidate membership comes from the current Excel list; historical delisted names are not reconstructed.")
    frames: list[pd.DataFrame] = []
    failed = 0
    for idx, info in enumerate(infos, start=1):
        try:
            bars = service.get_ohlcv(info.ticker, history_start, actual_end, market_hint=info.market, allow_etf=False, fallback_yfinance=True)
            if bars.empty:
                raise RuntimeError("empty bars")
            part = bars.reset_index()
            part = part.rename(columns={part.columns[0]: "date"})
            part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
            part["ticker"] = info.ticker
            part["name"] = info.name
            part["market"] = info.market
            frames.append(part[["date", "ticker", "name", "market", "trading_value", "volume", "close"]])
        except Exception:
            failed += 1
        if idx == 1 or idx == len(infos) or idx % 50 == 0:
            print(f"[FALLBACK] ticker {idx}/{len(infos)} loaded={len(frames):,} failed={failed:,}")
    if not frames:
        raise RuntimeError("Fallback에서도 종목별 OHLCV를 확보하지 못했습니다.")
    return _rank_raw_liquidity(pd.concat(frames, ignore_index=True), start, actual_end, top_n, lookback)


def _market_calendar_dates(service: MarketDataService, market: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    index_df = service.get_market_index(market, start, end)
    dates = pd.DatetimeIndex(pd.to_datetime(index_df.index, errors="coerce")).dropna()
    dates = dates[(dates.normalize() >= start) & (dates.normalize() <= end)]
    return pd.DatetimeIndex(sorted({pd.Timestamp(x).normalize() for x in dates}))


def _per_ticker_market_close_history(service: MarketDataService, start: pd.Timestamp, end: pd.Timestamp, market: str, *, info_excel: str | Path, expected_dates: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict]:
    infos = ExcelUniverseService(info_excel).get_universe(top_n=0, include_etf=False, markets=(market,))
    print(f"[FALLBACK] {market} market close history -> per-ticker OHLCV | current Excel membership={len(infos):,}")
    print("[WARN] Historical membership is not reconstructed in this fallback. Use as BACKTEST_ONLY unless separately validated.")
    frames: list[pd.DataFrame] = []
    failed_tickers = 0
    total = len(infos)
    for idx, info in enumerate(infos, start=1):
        try:
            bars = service.get_ohlcv(info.ticker, start, end, market_hint=market, allow_etf=False, fallback_yfinance=True)
            if bars is None or bars.empty or "close" not in bars.columns:
                raise RuntimeError("empty close history")
            part = bars[["close"]].copy().reset_index()
            part = part.rename(columns={part.columns[0]: "date"})
            part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
            part["ticker"] = str(info.ticker).zfill(6)
            part["close"] = pd.to_numeric(part["close"], errors="coerce")
            part = part.dropna(subset=["date", "close"])
            part = part[(part["date"] >= start) & (part["date"] <= end) & (part["close"] > 0)]
            if not part.empty:
                frames.append(part[["date", "ticker", "close"]])
        except Exception:
            failed_tickers += 1
        if idx == 1 or idx == total or idx % 50 == 0:
            print(f"[FALLBACK] {market} ticker {idx}/{total} loaded={len(frames):,} failed={failed_tickers:,}")
    if not frames:
        raise RuntimeError(f"{market} per-ticker market close history fallback failed")
    source = pd.concat(frames, ignore_index=True).drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"]).reset_index(drop=True)
    loaded_dates = int(source["date"].nunique())
    expected_count = int(len(expected_dates))
    return source, {
        "expected_dates": expected_count,
        "loaded_dates": loaded_dates,
        "failed_dates": max(0, expected_count - loaded_dates),
        "source_mode": "PER_TICKER_CURRENT_UNIVERSE_FALLBACK",
        "membership_mode": "CURRENT_EXCEL_UNIVERSE",
        "ticker_count": int(total),
        "failed_tickers": int(failed_tickers),
    }


def build_market_close_history(start, end, market: str, *, info_excel: str | Path = DEFAULT_INFO_XLSX, service: MarketDataService | None = None, snapshot_fail_fast: int = 2, allow_current_universe_fallback: bool = True) -> tuple[pd.DataFrame, dict]:
    """Build long-form market close history for breadth-style calculations.

    Preferred source is KRX all-ticker daily snapshots, which preserve point-in-time
    market membership. If KRX/pykrx repeatedly fails on the all-ticker endpoints,
    fall back to per-ticker historical OHLCV using the current Excel universe.
    The fallback preserves historical prices but not historical membership.
    """
    market_key = str(market).upper()
    if market_key not in {"KOSPI", "KOSDAQ"}:
        raise ValueError(f"market must be KOSPI/KOSDAQ: {market}")
    start_ts = pd.Timestamp(start).normalize()
    end_ts = min(pd.Timestamp(end).normalize(), pd.Timestamp.today().normalize())
    if start_ts > end_ts:
        raise ValueError(f"start > end: {start_ts.date()} > {end_ts.date()}")
    svc = service or get_market_data_service()
    dates = _market_calendar_dates(svc, market_key, start_ts, end_ts)
    if len(dates) == 0:
        raise RuntimeError(f"{market_key} market calendar is empty: {start_ts.date()}~{end_ts.date()}")

    fail_limit = max(1, int(snapshot_fail_fast))
    frames: list[pd.DataFrame] = []
    failures = 0
    first_error: Exception | None = None
    total = len(dates)
    print(f"[INFO] {market_key} market close history | dates={total} | primary=KRX all-ticker snapshot")

    for idx, dt in enumerate(dates, start=1):
        try:
            snap = svc.get_market_snapshot(dt.strftime("%Y%m%d"), market_key, retries=1)
            if snap is None or snap.empty or not {"ticker", "close"}.issubset(snap.columns):
                raise RuntimeError("snapshot missing ticker/close")
            day = snap[["ticker", "close"]].copy()
            day["ticker"] = day["ticker"].astype(str).str.zfill(6)
            day["close"] = pd.to_numeric(day["close"], errors="coerce")
            day = day.dropna(subset=["close"])
            day = day[day["close"] > 0]
            day["date"] = dt
            frames.append(day[["date", "ticker", "close"]])
        except Exception as exc:
            failures += 1
            if first_error is None:
                first_error = exc
            if failures >= fail_limit:
                if not allow_current_universe_fallback:
                    raise RuntimeError(f"{market_key} all-ticker snapshot failed {failures} times and fallback is disabled") from exc
                print(f"[WARN] {market_key} all-ticker snapshot failed {failures} times; switching to per-ticker history fallback.")
                print(f"[WARN] First snapshot error: {type(first_error).__name__}: {first_error}")
                return _per_ticker_market_close_history(svc, start_ts, end_ts, market_key, info_excel=info_excel, expected_dates=dates)
        if idx == total or idx % 50 == 0:
            print(f"[INFO] {market_key} snapshots {idx}/{total} | loaded={len(frames)} | failed={failures}")

    if not frames:
        raise RuntimeError(f"{market_key} all-ticker snapshots returned no usable data")
    source = pd.concat(frames, ignore_index=True).drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"]).reset_index(drop=True)
    loaded_dates = int(source["date"].nunique())
    return source, {
        "expected_dates": int(total),
        "loaded_dates": loaded_dates,
        "failed_dates": int(failures),
        "source_mode": "ALL_TICKER_SNAPSHOT" if failures == 0 else "ALL_TICKER_SNAPSHOT_PARTIAL",
        "membership_mode": "POINT_IN_TIME_SNAPSHOT",
        "ticker_count": int(source["ticker"].nunique()),
        "failed_tickers": 0,
    }


def build_liquidity_universe(start, end, top_n: int = 200, lookback: int = 20, markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"), *, info_excel: str | Path = DEFAULT_INFO_XLSX, service: MarketDataService | None = None) -> pd.DataFrame:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = min(pd.Timestamp(end).normalize(), pd.Timestamp.today().normalize())
    if start_ts > end_ts:
        raise ValueError(f"start > end: {start_ts.date()} > {end_ts.date()}")
    if int(top_n) <= 0 or int(lookback) <= 0:
        raise ValueError("top_n/lookback은 1 이상이어야 합니다.")
    normalized_markets = tuple(str(x).upper() for x in markets if str(x).strip())
    if not normalized_markets:
        raise ValueError("markets가 비어 있습니다.")
    svc = service or get_market_data_service()
    try:
        return _snapshot_path(svc, start_ts, end_ts, int(top_n), int(lookback), normalized_markets, info_excel)
    except Exception as exc:
        print(f"[WARN] KRX all-ticker snapshot path failed: {type(exc).__name__}: {exc}")
        return _per_ticker_fallback(svc, start_ts, end_ts, int(top_n), int(lookback), normalized_markets, info_excel)
