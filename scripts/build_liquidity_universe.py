from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import os
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / "cache" / "liquidity_universe"
DEFAULT_OUTPUT_ROOT = ROOT / "results" / "liquidity_universe"
DEFAULT_INFO_XLSX = ROOT / "KJBChartAnalyzer" / "KOSPI_Info.xlsx"

_KRX_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
_KRX_REFERER = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
_KRX_HTTP_SESSION: requests.Session | None = None
_PYKRX_STOCK = None


def _new_krx_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _KRX_USER_AGENT,
            "Referer": _KRX_REFERER,
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    try:
        session.get(_KRX_REFERER, timeout=10)
    except requests.RequestException:
        pass
    return session


def _reset_krx_http_session() -> requests.Session:
    global _KRX_HTTP_SESSION
    if _KRX_HTTP_SESSION is not None:
        try:
            _KRX_HTTP_SESSION.close()
        except Exception:
            pass
    _KRX_HTTP_SESSION = _new_krx_http_session()
    return _KRX_HTTP_SESSION


def _install_shared_pykrx_transport(webio) -> None:
    _reset_krx_http_session()

    def _session_post_read(self, **params):
        session = _KRX_HTTP_SESSION or _reset_krx_http_session()
        headers = dict(getattr(self, "headers", {}) or {})
        headers.setdefault("User-Agent", _KRX_USER_AGENT)
        headers.setdefault("Referer", _KRX_REFERER)
        headers.setdefault("X-Requested-With", "XMLHttpRequest")
        return session.post(self.url, headers=headers, data=params, timeout=30)

    def _session_get_read(self, **params):
        session = _KRX_HTTP_SESSION or _reset_krx_http_session()
        headers = dict(getattr(self, "headers", {}) or {})
        headers.setdefault("User-Agent", _KRX_USER_AGENT)
        headers.setdefault("Referer", _KRX_REFERER)
        headers.setdefault("X-Requested-With", "XMLHttpRequest")
        return session.get(self.url, headers=headers, params=params, timeout=30)

    webio.Post.read = _session_post_read
    webio.Get.read = _session_get_read


def _load_pykrx():
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
        raise RuntimeError("pykrx가 필요합니다. 각 Analyzer의 requirements.txt를 설치하세요.") from exc
    finally:
        for key, value in saved_env.items():
            if value is not None:
                os.environ[key] = value

    _install_shared_pykrx_transport(webio)
    _PYKRX_STOCK = stock
    print("[INFO] KRX transport: shared requests.Session enabled (pykrx auto-login bypassed).")
    return stock


def _parse_date(text: str) -> pd.Timestamp:
    raw = str(text or "").strip().replace("-", "")
    return pd.to_datetime(raw, format="%Y%m%d", errors="raise").normalize()


def _parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    raw = str(text or "").strip().replace(" ", "")
    if "~" not in raw:
        raise ValueError("--date-range은 YYYYMMDD~YYYYMMDD 형식이어야 합니다.")
    left, right = raw.split("~", 1)
    start, end = _parse_date(left), _parse_date(right)
    if start > end:
        raise ValueError(f"시작일이 종료일보다 늦습니다: {start.date()} > {end.date()}")
    return start, end


def _ticker(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text else ""


def _normalize_market(value: object) -> str:
    text = str(value or "").strip().upper()
    if "KOSDAQ" in text:
        return "KOSDAQ"
    if "KOSPI" in text:
        return "KOSPI"
    return text


def _snapshot_cache_path(cache_dir: Path, market: str, date: pd.Timestamp) -> Path:
    return cache_dir / f"{market.upper()}_{date:%Y%m%d}.csv"


def _normalize_snapshot(raw: pd.DataFrame, market: str, date: pd.Timestamp) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "ticker", "market", "trading_value", "volume", "close"])
    x = raw.copy()
    rename = {}
    for col in x.columns:
        key = str(col).strip()
        low = key.lower()
        if key == "거래대금" or low in {"trading_value", "value"}:
            rename[col] = "trading_value"
        elif key == "거래량" or low == "volume":
            rename[col] = "volume"
        elif key == "종가" or low == "close":
            rename[col] = "close"
    x = x.rename(columns=rename)
    x["ticker"] = [_ticker(v) for v in x.index]
    for col in ("trading_value", "volume", "close"):
        if col in x.columns:
            x[col] = pd.to_numeric(x[col], errors="coerce")
    if "trading_value" not in x.columns:
        if {"close", "volume"}.issubset(x.columns):
            x["trading_value"] = x["close"] * x["volume"]
        else:
            raise ValueError(f"{market} {date:%Y-%m-%d} snapshot에 거래대금 컬럼이 없습니다: {list(raw.columns)}")
    if "volume" not in x.columns:
        x["volume"] = pd.NA
    if "close" not in x.columns:
        x["close"] = pd.NA
    x["date"] = date.normalize()
    x["market"] = market.upper()
    x = x[["date", "ticker", "market", "trading_value", "volume", "close"]].copy()
    x = x[x["ticker"].str.fullmatch(r"\d{6}", na=False)]
    return x.drop_duplicates(["date", "ticker"], keep="last").reset_index(drop=True)


def _fetch_snapshot(stock, date: pd.Timestamp, market: str, cache_dir: Path, retries: int = 3) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _snapshot_cache_path(cache_dir, market, date)
    if cache_path.exists():
        try:
            cached = pd.read_csv(cache_path, encoding="utf-8-sig", dtype={"ticker": str})
            if not cached.empty:
                cached["date"] = pd.to_datetime(cached["date"], errors="coerce").dt.normalize()
                cached["ticker"] = cached["ticker"].map(_ticker)
                return cached
        except Exception:
            pass

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                if market.upper() == "ETF":
                    raw = stock.get_etf_ohlcv_by_ticker(date.strftime("%Y%m%d"))
                else:
                    raw = stock.get_market_ohlcv_by_ticker(date.strftime("%Y%m%d"), market=market)
            out = _normalize_snapshot(raw, market, date)
            if out.empty:
                raise ValueError("빈 market snapshot")
            out.to_csv(cache_path, index=False, encoding="utf-8-sig")
            return out
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                _reset_krx_http_session()
                time.sleep(0.7 * attempt)
    raise RuntimeError(
        f"{market} {date:%Y-%m-%d} 거래대금 snapshot 조회 실패 after {retries} attempts: "
        f"{type(last_exc).__name__}: {last_exc}"
    ) from last_exc


def _trading_dates(stock, start: pd.Timestamp, end: pd.Timestamp, lookback: int) -> list[pd.Timestamp]:
    extra_days = max(90, int(lookback) * 6)
    for multiplier in (1, 2, 4):
        fetch_start = start - pd.Timedelta(days=extra_days * multiplier)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                raw = stock.get_market_ohlcv_by_date(
                    fetch_start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), "005930", adjusted=True
                )
        except Exception:
            raw = pd.DataFrame()
        if raw is None or raw.empty:
            continue
        dates = sorted(pd.to_datetime(raw.index).normalize().unique())
        target = [pd.Timestamp(d) for d in dates if start <= pd.Timestamp(d) <= end]
        if not target and start == end:
            prev = [pd.Timestamp(d) for d in dates if pd.Timestamp(d) <= end]
            if prev:
                target = [prev[-1]]
        if not target:
            continue
        first_idx = dates.index(target[0].to_datetime64())
        if first_idx >= lookback - 1:
            warm_start = first_idx - lookback + 1
            last_idx = dates.index(target[-1].to_datetime64())
            return [pd.Timestamp(d) for d in dates[warm_start:last_idx + 1]]
    raise RuntimeError("거래일 캘린더를 확보하지 못했습니다. pykrx 조회 상태를 확인하세요.")


def _add_names(stock, daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    names: dict[str, str] = {}
    for _, row in out[["ticker", "market"]].drop_duplicates().iterrows():
        ticker = str(row["ticker"])
        market = str(row["market"]).upper()
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                name = stock.get_market_ticker_name(ticker)
            name = str(name or "").strip()
        except Exception:
            name = ""
        names[ticker] = name or ticker
    out["name"] = out["ticker"].map(names)
    return out


def _find_column(df: pd.DataFrame, names: tuple[str, ...], required: bool = True) -> str | None:
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    if required:
        raise ValueError(f"필수 컬럼을 찾지 못했습니다: {names}; columns={list(df.columns)}")
    return None


def _load_candidate_universe(info_path: Path, markets: tuple[str, ...]) -> pd.DataFrame:
    if not info_path.exists():
        raise FileNotFoundError(f"종목 Universe Excel을 찾지 못했습니다: {info_path}")
    df = pd.read_excel(info_path)
    ticker_col = _find_column(df, ("Ticker", "ticker", "종목코드", "코드"))
    name_col = _find_column(df, ("Name", "name", "종목명", "회사명"), required=False)
    market_col = _find_column(df, ("시장", "market", "Market"), required=False)

    out = pd.DataFrame()
    out["ticker"] = df[ticker_col].map(_ticker)
    out["name"] = df[name_col].fillna("").astype(str).str.strip() if name_col else out["ticker"]
    out["market"] = df[market_col].map(_normalize_market) if market_col else "KOSPI"

    wanted = {str(x).upper() for x in markets}
    out = out[out["market"].isin(wanted)].copy()
    out = out[out["ticker"].str.fullmatch(r"\d{6}", na=False)]
    upper_name = out["name"].fillna("").astype(str).str.upper()
    etp_prefix = r"^(KODEX|TIGER|ACE|RISE|KBSTAR|SOL|PLUS|HANARO|TIMEFOLIO|KOACT|WOORI|ARIRANG|BNK|HK|VITA|히어로즈|마이다스)"
    etp_mask = (
        upper_name.str.contains(r"\bETF\b|\bETN\b|\bETP\b", regex=True, na=False)
        | upper_name.str.match(etp_prefix, na=False)
    )
    out = out[~etp_mask].drop_duplicates("ticker", keep="first").reset_index(drop=True)
    if out.empty:
        raise RuntimeError(f"KOSPI_Info.xlsx에서 대상 시장 종목을 찾지 못했습니다: {sorted(wanted)}")
    return out[["ticker", "name", "market"]]


def _series_cache_path(cache_dir: Path, ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> Path:
    series_dir = cache_dir / "ticker_series"
    series_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(f"{ticker}_{start:%Y%m%d}_{end:%Y%m%d}".encode("utf-8")).hexdigest()[:10]
    return series_dir / f"{ticker}_{digest}.csv"


def _normalize_ticker_series(raw: pd.DataFrame, ticker: str, name: str, market: str) -> pd.DataFrame:
    cols = ["date", "ticker", "name", "market", "trading_value", "volume", "close"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=cols)
    x = raw.copy()
    if isinstance(x.columns, pd.MultiIndex):
        known = {"open", "high", "low", "close", "volume", "adj close"}
        flat = []
        for col in x.columns:
            parts = [str(part) for part in col]
            flat.append(next((part for part in parts if part.strip().lower() in known), parts[-1]))
        x.columns = flat

    rename = {}
    for col in x.columns:
        key = str(col).strip()
        low = key.lower().replace("_", " ")
        if key == "거래대금" or low in {"trading value", "value"}:
            rename[col] = "trading_value"
        elif key == "거래량" or low == "volume":
            rename[col] = "volume"
        elif key == "종가" or low == "close":
            rename[col] = "close"
    x = x.rename(columns=rename)
    if "close" not in x.columns or "volume" not in x.columns:
        return pd.DataFrame(columns=cols)

    close = pd.to_numeric(x["close"], errors="coerce")
    volume = pd.to_numeric(x["volume"], errors="coerce")
    trading_value = (
        pd.to_numeric(x["trading_value"], errors="coerce")
        if "trading_value" in x.columns
        else close * volume
    )
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(x.index, errors="coerce"),
            "ticker": _ticker(ticker),
            "name": str(name or ticker),
            "market": _normalize_market(market),
            "trading_value": trading_value.to_numpy(),
            "volume": volume.to_numpy(),
            "close": close.to_numpy(),
        }
    )
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out = out.dropna(subset=["date", "close"])
    out = out[pd.to_numeric(out["close"], errors="coerce").gt(0)]
    return out.drop_duplicates(["date", "ticker"], keep="last").sort_values("date").reset_index(drop=True)


def _fetch_ticker_series(stock, rec, start: pd.Timestamp, end: pd.Timestamp, cache_dir: Path) -> tuple[pd.DataFrame, str]:
    cache_path = _series_cache_path(cache_dir, str(rec.ticker), start, end)
    if cache_path.exists():
        try:
            cached = pd.read_csv(cache_path, encoding="utf-8-sig", dtype={"ticker": str})
            cached["date"] = pd.to_datetime(cached["date"], errors="coerce").dt.normalize()
            if not cached.empty:
                return cached, "cache"
        except Exception:
            pass

    pykrx_exc: Exception | None = None
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            raw = stock.get_market_ohlcv_by_date(
                start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), str(rec.ticker), adjusted=True
            )
        out = _normalize_ticker_series(raw, rec.ticker, rec.name, rec.market)
        if not out.empty:
            out.to_csv(cache_path, index=False, encoding="utf-8-sig")
            return out, "pykrx"
    except Exception as exc:
        pykrx_exc = exc

    try:
        import yfinance as yf

        suffix = "KQ" if str(rec.market).upper() == "KOSDAQ" else "KS"
        symbol = f"{str(rec.ticker).zfill(6)}.{suffix}"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            raw = yf.download(
                symbol,
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=False,
            )
        out = _normalize_ticker_series(raw, rec.ticker, rec.name, rec.market)
        if not out.empty:
            out.to_csv(cache_path, index=False, encoding="utf-8-sig")
            return out, "yfinance"
    except Exception:
        pass

    if pykrx_exc is not None:
        return pd.DataFrame(), f"failed:{type(pykrx_exc).__name__}"
    return pd.DataFrame(), "failed"


def _rank_raw_liquidity(
    raw: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    top_n: int,
    lookback: int,
) -> pd.DataFrame:
    if raw.empty:
        raise RuntimeError("거래대금 원천 데이터가 비어 있습니다.")
    raw = raw.drop_duplicates(["date", "ticker"], keep="last").copy()
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce").dt.normalize()
    raw["ticker"] = raw["ticker"].map(_ticker)
    raw["trading_value"] = pd.to_numeric(raw["trading_value"], errors="coerce").fillna(0.0)
    raw = raw.sort_values(["ticker", "date"]).reset_index(drop=True)
    raw["avg_trading_value_20d"] = (
        raw.groupby("ticker", group_keys=False)["trading_value"]
        .rolling(window=lookback, min_periods=lookback)
        .mean()
        .reset_index(level=0, drop=True)
    )

    if start == end:
        available = sorted(raw.loc[raw["date"] <= end, "date"].dropna().unique())
        if not available:
            raise RuntimeError("기준일 이전의 거래일을 찾지 못했습니다.")
        target_dates = [pd.Timestamp(available[-1]).normalize()]
    else:
        target_dates = [
            pd.Timestamp(d).normalize()
            for d in sorted(raw.loc[(raw["date"] >= start) & (raw["date"] <= end), "date"].dropna().unique())
        ]

    selected: list[pd.DataFrame] = []
    for idx, date in enumerate(target_dates, start=1):
        day = raw[raw["date"].eq(date)].copy()
        day = day[day["avg_trading_value_20d"].notna() & day["avg_trading_value_20d"].gt(0)]
        day = day.sort_values(
            ["avg_trading_value_20d", "trading_value", "ticker"], ascending=[False, False, True]
        ).head(top_n)
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
        raise RuntimeError("20거래일 평균 거래대금 Universe를 만들지 못했습니다.")
    daily = pd.concat(selected, ignore_index=True)
    if "name" not in daily.columns:
        daily["name"] = daily["ticker"]
    return daily[
        [
            "date",
            "source_rank",
            "ticker",
            "name",
            "market",
            "trading_value",
            "avg_trading_value_20d",
            "universe_cutoff_value",
            "lookback_days",
            "volume",
            "close",
        ]
    ].sort_values(["date", "source_rank"]).reset_index(drop=True)


def _build_from_ticker_series(
    stock,
    start: pd.Timestamp,
    end: pd.Timestamp,
    top_n: int,
    lookback: int,
    markets: tuple[str, ...],
    cache_dir: Path,
) -> pd.DataFrame:
    candidates = _load_candidate_universe(DEFAULT_INFO_XLSX, markets)
    history_start = start - pd.Timedelta(days=max(120, int(lookback) * 8))
    actual_end = min(end, pd.Timestamp.today().normalize())

    print("[FALLBACK] KRX all-ticker snapshot unavailable -> switching to per-ticker range OHLCV.")
    print(f"[FALLBACK] Candidate list: {DEFAULT_INFO_XLSX}")
    print(f"[FALLBACK] Candidate tickers: {len(candidates):,}")
    print("[INFO] Ranking remains date-wise recent-20-trading-day average trading value.")
    print("[INFO] Current KOSPI_Info.xlsx is the candidate list; historical delisted names cannot be reconstructed.")

    frames: list[pd.DataFrame] = []
    provider_counts: dict[str, int] = {}
    failed = 0
    total = len(candidates)
    for idx, rec in enumerate(candidates.itertuples(index=False), start=1):
        out, provider = _fetch_ticker_series(stock, rec, history_start, actual_end, cache_dir)
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        if out.empty:
            failed += 1
        else:
            frames.append(out)
        if idx == 1 or idx == total or idx % 50 == 0:
            print(
                f"[FALLBACK] ticker {idx}/{total} loaded={len(frames):,} failed={failed:,} "
                f"cache={provider_counts.get('cache', 0):,} pykrx={provider_counts.get('pykrx', 0):,} "
                f"yfinance={provider_counts.get('yfinance', 0):,}"
            )
        if idx % 25 == 0:
            time.sleep(0.03)

    if not frames:
        raise RuntimeError("Fallback에서도 종목별 OHLCV를 확보하지 못했습니다.")
    raw = pd.concat(frames, ignore_index=True)
    return _rank_raw_liquidity(raw, start, actual_end, top_n, lookback)


def build_liquidity_universe(
    start: pd.Timestamp,
    end: pd.Timestamp,
    top_n: int = 200,
    lookback: int = 20,
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> pd.DataFrame:
    if top_n <= 0:
        raise ValueError("top_n은 1 이상이어야 합니다.")
    if lookback <= 0:
        raise ValueError("lookback은 1 이상이어야 합니다.")

    stock = _load_pykrx()
    try:
        dates = _trading_dates(stock, start, end, lookback)
        frames = []
        total = len(dates)
        for idx, date in enumerate(dates, start=1):
            day = pd.concat(
                [_fetch_snapshot(stock, date, market, cache_dir) for market in markets],
                ignore_index=True,
            )
            frames.append(day)
            if idx == 1 or idx == total or idx % 20 == 0:
                print(f"[LIQUIDITY] snapshot {idx}/{total} {date:%Y-%m-%d} rows={len(day)}")
        raw = pd.concat(frames, ignore_index=True)
        daily = _rank_raw_liquidity(raw, start, end, top_n, lookback)
        daily = _add_names(stock, daily)
        return daily
    except Exception as exc:
        print(
            f"[WARN] KRX all-ticker snapshot path failed: {type(exc).__name__}: {exc}"
        )
        return _build_from_ticker_series(stock, start, end, top_n, lookback, markets, cache_dir)


def _build_union_excel(daily: pd.DataFrame) -> pd.DataFrame:
    ordered = daily.sort_values(["date", "source_rank"]).copy()
    latest = ordered.groupby("ticker", as_index=False).tail(1).copy()
    stats = ordered.groupby("ticker", as_index=False).agg(
        universe_best_rank=("source_rank", "min"),
        universe_membership_days=("date", "nunique"),
    )
    union = latest.merge(stats, on="ticker", how="left").sort_values(
        ["universe_best_rank", "avg_trading_value_20d", "ticker"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    return pd.DataFrame(
        {
            "Ticker": union["ticker"],
            "Name": union["name"],
            "시장": union["market"],
            "시가총액": pd.NA,
            "거래대금": union["avg_trading_value_20d"],
            "거래량": union["volume"],
            "최근20일평균거래대금": union["avg_trading_value_20d"],
            "당일거래대금": union["trading_value"],
            "유니버스최고순위": union["universe_best_rank"],
            "유니버스포함일수": union["universe_membership_days"],
            "최근포함일": union["date"].dt.strftime("%Y-%m-%d"),
        }
    )


def _write_env(
    path: Path,
    universe_xlsx: Path,
    membership_csv: Path,
    actual_as_of: pd.Timestamp,
    top_n: int,
    lookback: int,
) -> None:
    lines = [
        f'set "LIQUIDITY_UNIVERSE_XLSX={universe_xlsx.resolve()}"',
        f'set "LIQUIDITY_MEMBERSHIP_CSV={membership_csv.resolve()}"',
        f'set "LIQUIDITY_AS_OF={actual_as_of:%Y%m%d}"',
        f'set "LIQUIDITY_TOP_N={int(top_n)}"',
        f'set "LIQUIDITY_LOOKBACK={int(lookback)}"',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="최근 N거래일 평균 거래대금 기반 날짜별 TOP N Universe 생성")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--date-range", default="")
    mode.add_argument("--as-of", default="")
    p.add_argument("--top-n", type=int, default=200)
    p.add_argument("--lookback", type=int, default=20)
    p.add_argument("--markets", default="KOSPI,KOSDAQ")
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    p.add_argument("--output-dir", default="")
    args = p.parse_args()

    if args.date_range:
        start, end = _parse_date_range(args.date_range)
        default_key = f"range_{start:%Y%m%d}_{end:%Y%m%d}"
    else:
        as_of = _parse_date(args.as_of) if args.as_of else pd.Timestamp.today().normalize()
        start = end = as_of
        default_key = "screen_latest"

    markets = tuple(x.strip().upper() for x in args.markets.split(",") if x.strip())
    if not markets:
        raise ValueError("--markets가 비어 있습니다.")
    out_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / default_key
    out_dir.mkdir(parents=True, exist_ok=True)

    daily = build_liquidity_universe(start, end, args.top_n, args.lookback, markets, Path(args.cache_dir))
    actual_as_of = pd.Timestamp(daily["date"].max()).normalize()
    membership_csv = out_dir / "liquidity_universe_daily.csv"
    union_xlsx = out_dir / "liquidity_universe_union.xlsx"
    env_path = out_dir / "liquidity_universe.env"
    daily.to_csv(membership_csv, index=False, encoding="utf-8-sig")
    _build_union_excel(daily).to_excel(union_xlsx, index=False)
    _write_env(env_path, union_xlsx, membership_csv, actual_as_of, args.top_n, args.lookback)

    print("=" * 72)
    print("[DONE] 최근 거래대금 Universe 생성")
    print(f"기준          : 최근 {args.lookback}거래일 평균 거래대금")
    print(f"시장          : {', '.join(markets)}")
    print(f"일별 TOP N    : {args.top_n}")
    print(f"거래일 수     : {daily['date'].nunique()}")
    print(f"Union 종목 수 : {daily['ticker'].nunique()}")
    print(f"실제 최종일   : {actual_as_of:%Y-%m-%d}")
    print(f"Membership    : {membership_csv}")
    print(f"Union Excel   : {union_xlsx}")
    print(f"Env           : {env_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
