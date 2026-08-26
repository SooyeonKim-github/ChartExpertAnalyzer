from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / "cache" / "liquidity_universe"
DEFAULT_OUTPUT_ROOT = ROOT / "results" / "liquidity_universe"


def _load_pykrx():
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx가 필요합니다. 각 Analyzer의 requirements.txt를 설치하세요.") from exc
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
    return text.zfill(6)


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
    x = x.drop_duplicates(["date", "ticker"], keep="last")
    return x.reset_index(drop=True)


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
            raw = stock.get_market_ohlcv_by_ticker(date.strftime("%Y%m%d"), market=market)
            out = _normalize_snapshot(raw, market, date)
            if out.empty:
                raise ValueError("빈 market snapshot")
            out.to_csv(cache_path, index=False, encoding="utf-8-sig")
            return out
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(0.5 * attempt)

    raise RuntimeError(
        f"{market} {date:%Y-%m-%d} 거래대금 snapshot 조회 실패"
    ) from last_exc


def _trading_dates(stock, start: pd.Timestamp, end: pd.Timestamp, lookback: int) -> list[pd.Timestamp]:
    # KOSPI/KOSDAQ의 거래일은 동일하므로 장기 상장 종목(삼성전자) 일봉을 거래 캘린더로 사용한다.
    # pykrx index endpoint 오류를 피하기 위한 선택이다.
    extra_days = max(90, int(lookback) * 6)
    for multiplier in (1, 2, 4):
        fetch_start = start - pd.Timedelta(days=extra_days * multiplier)
        try:
            raw = stock.get_market_ohlcv_by_date(
                fetch_start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
                "005930",
                adjusted=True,
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
            return [pd.Timestamp(d) for d in dates[warm_start : last_idx + 1]]

    raise RuntimeError("거래일 캘린더를 확보하지 못했습니다. pykrx 조회 상태를 확인하세요.")


def _name_map(stock, tickers: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ticker in tickers:
        try:
            name = str(stock.get_market_ticker_name(ticker) or "").strip()
        except Exception:
            name = ""
        out[ticker] = name or ticker
    return out


def build_liquidity_universe(
    start: pd.Timestamp,
    end: pd.Timestamp,
    top_n: int = 100,
    lookback: int = 20,
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> pd.DataFrame:
    if top_n <= 0:
        raise ValueError("top_n은 1 이상이어야 합니다.")
    if lookback <= 0:
        raise ValueError("lookback은 1 이상이어야 합니다.")

    stock = _load_pykrx()
    dates = _trading_dates(stock, start, end, lookback)
    target_start = start
    target_end = end

    frames: list[pd.DataFrame] = []
    total = len(dates)
    for idx, date in enumerate(dates, start=1):
        day_frames = []
        for market in markets:
            day_frames.append(_fetch_snapshot(stock, date, market, cache_dir))
        day = pd.concat(day_frames, ignore_index=True)
        frames.append(day)
        if idx == 1 or idx == total or idx % 20 == 0:
            print(f"[LIQUIDITY] snapshot {idx}/{total} {date:%Y-%m-%d} rows={len(day)}")

    raw = pd.concat(frames, ignore_index=True)
    raw["ticker"] = raw["ticker"].map(_ticker)
    raw["trading_value"] = pd.to_numeric(raw["trading_value"], errors="coerce").fillna(0.0)
    raw = raw.sort_values(["ticker", "date"]).reset_index(drop=True)
    raw["avg_trading_value_20d"] = (
        raw.groupby("ticker", group_keys=False)["trading_value"]
        .rolling(window=lookback, min_periods=lookback)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # screen 요청일이 휴일이면 거래 캘린더에서 선택한 직전 거래일을 실제 기준일로 사용한다.
    if start == end:
        available_target_dates = sorted(raw.loc[raw["date"] <= end, "date"].dropna().unique())
        if not available_target_dates:
            raise RuntimeError("기준일 이전의 거래일을 찾지 못했습니다.")
        target_dates = [pd.Timestamp(available_target_dates[-1]).normalize()]
    else:
        target_dates = [
            pd.Timestamp(d).normalize()
            for d in sorted(raw.loc[(raw["date"] >= target_start) & (raw["date"] <= target_end), "date"].dropna().unique())
        ]

    if not target_dates:
        raise RuntimeError("입력 기간에 거래일이 없습니다.")

    selected: list[pd.DataFrame] = []
    for date in target_dates:
        day = raw[raw["date"].eq(date)].copy()
        day = day[day["avg_trading_value_20d"].notna() & day["avg_trading_value_20d"].gt(0)]
        day = day.sort_values(
            ["avg_trading_value_20d", "trading_value", "ticker"],
            ascending=[False, False, True],
        ).head(top_n)
        if day.empty:
            continue
        day = day.reset_index(drop=True)
        day["source_rank"] = range(1, len(day) + 1)
        day["universe_cutoff_value"] = float(day["avg_trading_value_20d"].iloc[-1])
        day["lookback_days"] = int(lookback)
        selected.append(day)

    if not selected:
        raise RuntimeError("20거래일 평균 거래대금 Universe를 만들지 못했습니다.")

    daily = pd.concat(selected, ignore_index=True)
    names = _name_map(stock, sorted(daily["ticker"].unique().tolist()))
    daily["name"] = daily["ticker"].map(names)
    daily = daily[
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
    return daily


def _build_union_excel(daily: pd.DataFrame) -> pd.DataFrame:
    ordered = daily.sort_values(["date", "source_rank"]).copy()
    latest = ordered.groupby("ticker", as_index=False).tail(1).copy()
    stats = (
        ordered.groupby("ticker", as_index=False)
        .agg(
            universe_best_rank=("source_rank", "min"),
            universe_membership_days=("date", "nunique"),
        )
    )
    union = latest.merge(stats, on="ticker", how="left")
    union = union.sort_values(
        ["universe_best_rank", "avg_trading_value_20d", "ticker"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    # 기존 Analyzer의 KOSPI_Info.xlsx reader를 그대로 재사용하기 위해 호환 컬럼으로 저장한다.
    # '거래대금' 컬럼에는 현재 당일값이 아니라 요청한 20거래일 평균 거래대금을 넣는다.
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
    p = argparse.ArgumentParser(description="최근 N거래일 평균 거래대금 기반 point-in-time TOP N Universe 생성")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--date-range", default="", help="YYYYMMDD~YYYYMMDD")
    mode.add_argument("--as-of", default="", help="YYYYMMDD; 휴일이면 직전 거래일")
    p.add_argument("--top-n", type=int, default=100)
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

    daily = build_liquidity_universe(
        start=start,
        end=end,
        top_n=args.top_n,
        lookback=args.lookback,
        markets=markets,
        cache_dir=Path(args.cache_dir),
    )
    actual_as_of = pd.Timestamp(daily["date"].max()).normalize()

    membership_csv = out_dir / "liquidity_universe_daily.csv"
    union_xlsx = out_dir / "liquidity_universe_union.xlsx"
    env_path = out_dir / "liquidity_universe.env"

    daily.to_csv(membership_csv, index=False, encoding="utf-8-sig")
    _build_union_excel(daily).to_excel(union_xlsx, index=False)
    _write_env(env_path, union_xlsx, membership_csv, actual_as_of, args.top_n, args.lookback)

    counts = daily.groupby("date")["ticker"].nunique()
    print("=" * 72)
    print("[DONE] 최근 거래대금 Universe 생성")
    print(f"기준          : 최근 {args.lookback}거래일 평균 거래대금")
    print(f"시장          : {', '.join(markets)}")
    print(f"일별 TOP N    : {args.top_n}")
    print(f"거래일 수     : {len(counts)}")
    print(f"Union 종목 수 : {daily['ticker'].nunique()}")
    print(f"실제 최종일   : {actual_as_of:%Y-%m-%d}")
    print(f"Membership    : {membership_csv}")
    print(f"Union Excel   : {union_xlsx}")
    print(f"Env           : {env_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
