from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from MarketData import MarketDataService, build_liquidity_universe  # noqa: E402

DEFAULT_OUTPUT_ROOT = ROOT / "results" / "liquidity_universe"
DEFAULT_CACHE_DIR = ROOT / "cache" / "MarketData"
DEFAULT_INFO_XLSX = ROOT / "KJBChartAnalyzer" / "KOSPI_Info.xlsx"


def _parse_date(text: str) -> pd.Timestamp:
    raw = str(text or "").strip().replace("-", "")
    return pd.to_datetime(raw, format="%Y%m%d", errors="raise").normalize()


def _parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    raw = str(text or "").strip().replace(" ", "")
    if "~" not in raw: raise ValueError("--date-range은 YYYYMMDD~YYYYMMDD 형식이어야 합니다.")
    left, right = raw.split("~", 1); start, end = _parse_date(left), _parse_date(right)
    if start > end: raise ValueError(f"시작일이 종료일보다 늦습니다: {start.date()} > {end.date()}")
    return start, end


def _build_union_excel(daily: pd.DataFrame) -> pd.DataFrame:
    ordered = daily.sort_values(["date", "source_rank"]).copy(); latest = ordered.groupby("ticker", as_index=False).tail(1).copy()
    stats = ordered.groupby("ticker", as_index=False).agg(universe_best_rank=("source_rank", "min"), universe_membership_days=("date", "nunique"))
    union = latest.merge(stats, on="ticker", how="left").sort_values(["universe_best_rank", "avg_trading_value_20d", "ticker"], ascending=[True, False, True]).reset_index(drop=True)
    return pd.DataFrame({
        "Ticker": union["ticker"], "Name": union["name"], "시장": union["market"], "시가총액": pd.NA,
        "거래대금": union["avg_trading_value_20d"], "거래량": union["volume"], "최근20일평균거래대금": union["avg_trading_value_20d"],
        "당일거래대금": union["trading_value"], "유니버스최고순위": union["universe_best_rank"], "유니버스포함일수": union["universe_membership_days"],
        "최근포함일": pd.to_datetime(union["date"]).dt.strftime("%Y-%m-%d"),
    })


def _write_env(path: Path, universe_xlsx: Path, membership_csv: Path, actual_as_of: pd.Timestamp, top_n: int, lookback: int) -> None:
    lines = [f'set "LIQUIDITY_UNIVERSE_XLSX={universe_xlsx.resolve()}"', f'set "LIQUIDITY_MEMBERSHIP_CSV={membership_csv.resolve()}"', f'set "LIQUIDITY_AS_OF={actual_as_of:%Y%m%d}"', f'set "LIQUIDITY_TOP_N={int(top_n)}"', f'set "LIQUIDITY_LOOKBACK={int(lookback)}"']
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="MarketData 공통 최근 N거래일 평균 거래대금 point-in-time Universe 생성")
    mode = p.add_mutually_exclusive_group(); mode.add_argument("--date-range", default=""); mode.add_argument("--as-of", default="")
    p.add_argument("--top-n", type=int, default=200); p.add_argument("--lookback", type=int, default=20); p.add_argument("--markets", default="KOSPI,KOSDAQ")
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR)); p.add_argument("--info-excel", default=str(DEFAULT_INFO_XLSX)); p.add_argument("--output-dir", default="")
    args = p.parse_args()
    if args.date_range: start, end = _parse_date_range(args.date_range); default_key = f"range_{start:%Y%m%d}_{end:%Y%m%d}"
    else: as_of = _parse_date(args.as_of) if args.as_of else pd.Timestamp.today().normalize(); start = end = as_of; default_key = "screen_latest"
    markets = tuple(x.strip().upper() for x in args.markets.split(",") if x.strip()); out_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / default_key; out_dir.mkdir(parents=True, exist_ok=True)
    print("[INFO] MarketData: shared OHLCV/index/universe service")
    service = MarketDataService(cache_dir=args.cache_dir, use_cache=True)
    daily = build_liquidity_universe(start, end, args.top_n, args.lookback, markets, info_excel=args.info_excel, service=service)
    actual_as_of = pd.Timestamp(daily["date"].max()).normalize(); membership_csv = out_dir / "liquidity_universe_daily.csv"; union_xlsx = out_dir / "liquidity_universe_union.xlsx"; env_path = out_dir / "liquidity_universe.env"
    daily.to_csv(membership_csv, index=False, encoding="utf-8-sig"); _build_union_excel(daily).to_excel(union_xlsx, index=False); _write_env(env_path, union_xlsx, membership_csv, actual_as_of, args.top_n, args.lookback)
    print("=" * 72); print("[DONE] MarketData liquidity universe"); print(f"기준          : 최근 {args.lookback}거래일 평균 거래대금"); print(f"시장          : {', '.join(markets)}"); print(f"일별 TOP N    : {args.top_n}"); print(f"거래일 수     : {daily['date'].nunique()}"); print(f"Union 종목 수 : {daily['ticker'].nunique()}"); print(f"실제 최종일   : {actual_as_of:%Y-%m-%d}"); print(f"Membership    : {membership_csv}"); print(f"Union Excel   : {union_xlsx}"); print(f"Env           : {env_path}"); print("=" * 72)
    return 0


if __name__ == "__main__": raise SystemExit(main())
