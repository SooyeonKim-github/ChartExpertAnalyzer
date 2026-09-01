from __future__ import annotations

import argparse
import os
import pandas as pd

from analyzer import PullbackAnalyzer
from config import DEFAULT_CONFIG, DEFAULT_INFO_EXCEL, RESULT_DIR
from data.pykrx_provider import PykrxDataProvider
from universe import TickerUniverse

STATUS_RANK = {"CONFIRMED": 0, "WATCH": 1, "REJECT": 2}
CANDIDATE_STATUSES = {"CONFIRMED", "WATCH"}


def _history_start(date_text: str) -> str:
    return (pd.Timestamp(date_text) - pd.Timedelta(days=DEFAULT_CONFIG.history_calendar_days)).strftime("%Y-%m-%d")


def _market_symbol(market: str) -> str:
    return "^KQ11" if "KOSDAQ" in str(market).upper() else "^KS11"


def scan(args) -> int:
    cfg = DEFAULT_CONFIG
    universe = TickerUniverse(args.info_excel).get(args.top_n, args.sort_by)
    provider = PykrxDataProvider(use_cache=not args.no_cache)
    analyzer = PullbackAnalyzer(cfg)
    rows = []
    start = _history_start(args.date)
    market_cache = {}
    print(f"[INFO] Pullback V1 scan date={args.date} universe={len(universe)} history_start={start}")

    for idx, info in enumerate(universe, 1):
        try:
            stock_df = provider.get_ohlcv_by_date(info.ticker, start, args.date)
            symbol = _market_symbol(info.market)
            if symbol not in market_cache:
                try:
                    market_cache[symbol] = provider.get_ohlcv_by_date(symbol, start, args.date)
                except Exception as exc:
                    print(f"[WARN] market {symbol}: {exc}")
                    market_cache[symbol] = None
            result = analyzer.analyze(info.ticker, info.name, info.market, args.date, stock_df, market_cache.get(symbol))
            rows.append(result.to_row())
            if idx % 25 == 0:
                print(f"[INFO] progress {idx}/{len(universe)}")
        except Exception as exc:
            print(f"[WARN] {info.ticker} {info.name}: {exc}")

    if not rows:
        print("[ERROR] 분석 결과가 없습니다.")
        return 1

    df = pd.DataFrame(rows)
    df["_rank"] = df["Status"].map(STATUS_RANK).fillna(9)
    df = df.sort_values(["_rank", "Score", "Timing_Score"], ascending=[True, False, False]).drop(columns="_rank")
    out_dir = RESULT_DIR / pd.Timestamp(args.date).strftime("%Y%m%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "scan_results.csv", index=False, encoding="utf-8-sig")
    candidates = df[df["Status"].isin(CANDIDATE_STATUSES)].copy()
    candidates.to_csv(out_dir / "candidates.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(out_dir / "pullback_candidates.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="AllResults", index=False)
        candidates.to_excel(writer, sheet_name="Candidates", index=False)
        pd.DataFrame([{"Parameter": k, "Value": v} for k, v in cfg.to_dict().items()]).to_excel(writer, sheet_name="Config", index=False)
    counts = df["Status"].value_counts()
    print(f"[DONE] {out_dir}")
    print(f"[INFO] CONFIRMED={int(counts.get('CONFIRMED', 0))} WATCH={int(counts.get('WATCH', 0))} REJECT={int(counts.get('REJECT', 0))}")
    if not candidates.empty:
        cols = ["Ticker", "Name", "Status", "Score", "Timing_Score", "Primary_Signal", "Pullback_Type",
                "Pullback_Sequence", "Pullback_Retracement_Ratio", "Nearest_Support",
                "Pullback_Volume_Ratio_Impulse", "RS_Score", "Stop_Distance_Pct"]
        cols = [c for c in cols if c in candidates.columns]
        print(candidates[cols].head(args.print_top).to_string(index=False))
    return 0


def explain(args) -> int:
    cfg = DEFAULT_CONFIG
    universe = TickerUniverse(args.info_excel).load()
    ticker = args.ticker.zfill(6)
    match = universe[universe["Ticker"].astype(str).str.zfill(6) == ticker]
    name = ticker if match.empty else str(match.iloc[0]["Name"])
    market = "KOSPI" if match.empty else str(match.iloc[0]["Market"])
    provider = PykrxDataProvider(use_cache=not args.no_cache)
    start = _history_start(args.date)
    stock_df = provider.get_ohlcv_by_date(ticker, start, args.date)
    try:
        market_df = provider.get_ohlcv_by_date(_market_symbol(market), start, args.date)
    except Exception:
        market_df = None
    result = PullbackAnalyzer(cfg).analyze(ticker, name, market, args.date, stock_df, market_df)
    print(pd.Series(result.to_row()).to_string())
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="PullbackAnalyzer V1 - independent lecture-derived pullback analyzer")
    sub = p.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--info-excel", default=os.environ.get("LIQUIDITY_UNIVERSE_XLSX", str(DEFAULT_INFO_EXCEL)))
    common.add_argument("--no-cache", action="store_true")

    s = sub.add_parser("scan", parents=[common])
    s.add_argument("--date", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    s.add_argument("--top-n", type=int, default=100)
    s.add_argument("--sort-by", default="trading_value", choices=["market_cap", "trading_value", "volume"])
    s.add_argument("--print-top", type=int, default=30)
    s.set_defaults(func=scan)

    e = sub.add_parser("explain", parents=[common])
    e.add_argument("--ticker", required=True)
    e.add_argument("--date", required=True)
    e.set_defaults(func=explain)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(args.func(args))
