from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KJB_ROOT = ROOT / "KJBChartAnalyzer"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(KJB_ROOT) not in sys.path:
    sys.path.insert(0, str(KJB_ROOT))

from chartsel.data.pykrx_provider import PykrxDataProvider  # noqa: E402
from chartsel.sector.sector_service import SectorBacktestService  # noqa: E402
from chartsel.universe.ticker_universe_service import TickerUniverseService  # noqa: E402

from CloseBetAnalyzer.analyzer import CloseBetAnalyzer  # noqa: E402
from CloseBetAnalyzer.config import DEFAULT_CONFIG  # noqa: E402


def parse_args() -> argparse.Namespace:
    default_universe = os.environ.get("LIQUIDITY_UNIVERSE_XLSX", str(KJB_ROOT / "KOSPI_Info.xlsx"))
    p = argparse.ArgumentParser(
        description="CloseBetAnalyzer V1 - completed daily data candidate scan + manual buy-day price guide"
    )
    p.add_argument("--info-excel", default=default_universe)
    p.add_argument("--sector-info-excel", default=str(KJB_ROOT / "KOSPI_Info.xlsx"))
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--sort-by", choices=["market_cap", "trading_value", "volume"], default="trading_value")
    p.add_argument("--history-days", type=int, default=520)
    p.add_argument("--as-of", default="", help="YYYYMMDD; blank means today")
    p.add_argument("--request-delay", type=float, default=0.02)
    p.add_argument("--output-root", default=str(HERE / "results"))
    return p.parse_args()


def _market_key(market: str) -> str:
    return "^KQ11" if "KOSDAQ" in str(market).upper() else "^KS11"


def main() -> int:
    args = parse_args()
    universe = TickerUniverseService(args.info_excel).get_universe(
        top_n=args.top_n,
        sort_by=args.sort_by,
        include_etf=False,
    )
    if not universe:
        print("[ERROR] CloseBet universe is empty.")
        return 1

    end = pd.to_datetime(args.as_of, format="%Y%m%d") if args.as_of else pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=max(260, int(args.history_days)))
    provider = PykrxDataProvider(cache_dir=HERE / "cache", use_cache=True)
    analyzer = CloseBetAnalyzer(DEFAULT_CONFIG)

    print("=" * 86)
    print("CloseBetAnalyzer V1")
    print("=" * 86)
    print(f"Universe   : TOP {len(universe)} by {args.sort_by}")
    print(f"Data end   : {end:%Y-%m-%d}")
    print("Selection  : completed daily data only")
    print("Buy day    : no intraday chart scoring; numeric price-action guide only")
    print("=" * 86)

    benchmarks: dict[str, pd.DataFrame] = {}
    for key in ("^KS11", "^KQ11"):
        try:
            benchmarks[key] = provider.get_ohlcv_by_date(key, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        except Exception as exc:
            print(f"[WARN] benchmark {key}: {exc}")
            benchmarks[key] = pd.DataFrame()

    price_cache: dict[str, pd.DataFrame] = {}
    errors: list[dict] = []
    for idx, info in enumerate(universe, 1):
        try:
            df = provider.get_ohlcv_by_date(
                info.ticker,
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
            )
            if len(df) < 130:
                raise ValueError(f"insufficient bars={len(df)}")
            price_cache[info.ticker] = df
        except Exception as exc:
            errors.append({"Ticker": info.ticker, "Name": info.name, "Stage": "LOAD", "Error": repr(exc)})
            print(f"[WARN] LOAD {info.ticker} {info.name}: {exc}")
        if idx % 25 == 0 or idx == len(universe):
            print(f"[INFO] price load {idx}/{len(universe)} ready={len(price_cache)}")
        time.sleep(max(0.0, float(args.request_delay)))

    sector_service = None
    try:
        sector_service = SectorBacktestService(args.sector_info_excel)
        sector_service.build(
            price_cache=price_cache,
            benchmark_cache=benchmarks,
            allowed_tickers=set(price_cache),
        )
        print(f"[INFO] sector context ready scope={sector_service.aggregation_scope}")
    except Exception as exc:
        print(f"[WARN] sector context disabled: {exc}")
        sector_service = None

    rows: list[dict] = []
    for idx, info in enumerate(universe, 1):
        df = price_cache.get(info.ticker)
        if df is None or df.empty:
            continue
        try:
            market_key = _market_key(info.market)
            market_df = benchmarks.get(market_key, pd.DataFrame())
            if market_df.empty:
                raise ValueError(f"benchmark missing: {market_key}")
            actual_date = pd.Timestamp(df.index[-1]).normalize()
            sector_ctx = (
                sector_service.context(info.ticker, actual_date, info.market)
                if sector_service is not None
                else None
            )
            result = analyzer.analyze(
                ticker=info.ticker,
                name=info.name,
                market=info.market,
                stock_df=df,
                market_df=market_df,
                sector_context=sector_ctx,
                source_rank=info.source_rank,
                universe_size=len(universe),
            )
            rows.append(result.to_dict())
        except Exception as exc:
            errors.append({"Ticker": info.ticker, "Name": info.name, "Stage": "ANALYZE", "Error": repr(exc)})
            print(f"[WARN] ANALYZE {info.ticker} {info.name}: {exc}")
        if idx % 25 == 0 or idx == len(universe):
            print(f"[INFO] analyze {idx}/{len(universe)} results={len(rows)}")

    if not rows:
        print("[ERROR] no CloseBet results.")
        return 1

    result_df = pd.DataFrame(rows)
    status_rank = {"STRONG_CONFIRMED": 0, "CONFIRMED": 1, "WATCH": 2, "REJECTED": 3}
    result_df["_status_rank"] = result_df["status"].map(status_rank).fillna(9)
    result_df = result_df.sort_values(
        ["_status_rank", "score", "source_rank", "ticker"],
        ascending=[True, False, True, True],
    ).drop(columns="_status_rank").reset_index(drop=True)

    candidates = result_df[result_df["status"].isin(["STRONG_CONFIRMED", "CONFIRMED", "WATCH"])].copy()
    guides = result_df[result_df["status"].isin(["STRONG_CONFIRMED", "CONFIRMED"])].copy()

    latest = pd.to_datetime(result_df["actual_date"], errors="coerce").max()
    out_key = latest.strftime("%Y%m%d") if pd.notna(latest) else end.strftime("%Y%m%d")
    out_dir = Path(args.output_root) / out_key
    out_dir.mkdir(parents=True, exist_ok=True)

    result_df.to_csv(out_dir / "scan_results.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(out_dir / "candidates.csv", index=False, encoding="utf-8-sig")
    guides.to_csv(out_dir / "buy_day_guides.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(errors, columns=["Ticker", "Name", "Stage", "Error"]).to_csv(
        out_dir / "errors.csv", index=False, encoding="utf-8-sig"
    )

    counts = result_df["status"].value_counts()
    print()
    print(f"[DONE] {out_dir}")
    print(
        f"[INFO] STRONG={int(counts.get('STRONG_CONFIRMED', 0))} "
        f"CONFIRMED={int(counts.get('CONFIRMED', 0))} "
        f"WATCH={int(counts.get('WATCH', 0))} "
        f"REJECTED={int(counts.get('REJECTED', 0))}"
    )
    if not guides.empty:
        display_cols = [
            "ticker",
            "name",
            "status",
            "score",
            "sector_name",
            "stock_rs_score",
            "guide_reference_close",
            "guide_hold_level",
            "guide_cancel_below",
            "guide_chase_above",
        ]
        print()
        print(guides[display_cols].head(30).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
