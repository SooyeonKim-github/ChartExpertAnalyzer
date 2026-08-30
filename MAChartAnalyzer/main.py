from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from analyzer import MAChartSignalAnalyzer
from config import DEFAULT_CONFIG, DEFAULT_INFO_EXCEL, RESULT_DIR
from data_provider import PykrxDataProvider
from universe import TickerUniverse


STATUS_RANK = {"CONFIRMED": 0, "WATCH": 1, "REJECTED": 2}


def _history_start(date_text: str) -> str:
    return (pd.Timestamp(date_text) - pd.Timedelta(days=DEFAULT_CONFIG.history_calendar_days)).strftime("%Y-%m-%d")


def scan(args) -> int:
    cfg = DEFAULT_CONFIG
    universe = TickerUniverse(args.info_excel).get(args.top_n, args.sort_by)
    provider = PykrxDataProvider(use_cache=not args.no_cache)
    analyzer = MAChartSignalAnalyzer(cfg)

    rows: list[dict] = []
    start = _history_start(args.date)
    print(f"[INFO] MA scan date={args.date} universe={len(universe)} history_start={start}")

    for idx, info in enumerate(universe, 1):
        try:
            df = provider.get_ohlcv(info.ticker, start, args.date)
            if df.empty:
                continue
            result = analyzer.analyze(
                info.ticker,
                info.name,
                info.market,
                args.date,
                df,
            )
            rows.append(result.to_row())
            if idx % 25 == 0:
                print(f"[INFO] progress {idx}/{len(universe)}")
        except Exception as exc:
            print(f"[WARN] {info.ticker} {info.name}: {exc}")

    if not rows:
        print("[ERROR] 분석 결과가 없습니다.")
        return 1

    result_df = pd.DataFrame(rows)
    result_df["_rank"] = result_df["Status"].map(STATUS_RANK).fillna(9)
    result_df = result_df.sort_values(
        ["_rank", "Score", "Timing_Score"],
        ascending=[True, False, False],
    ).drop(columns="_rank")

    out_dir = RESULT_DIR / pd.Timestamp(args.date).strftime("%Y%m%d")
    out_dir.mkdir(parents=True, exist_ok=True)

    result_df.to_csv(out_dir / "scan_results.csv", index=False, encoding="utf-8-sig")
    candidates = result_df[result_df["Status"].isin(["CONFIRMED", "WATCH"])].copy()
    candidates.to_csv(out_dir / "candidates.csv", index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(out_dir / "ma_candidates.xlsx", engine="openpyxl") as writer:
        result_df.to_excel(writer, sheet_name="AllResults", index=False)
        candidates.to_excel(writer, sheet_name="Candidates", index=False)
        pd.DataFrame(
            [{"Parameter": k, "Value": v} for k, v in cfg.to_dict().items()]
        ).to_excel(writer, sheet_name="Config", index=False)

    print(f"[DONE] {out_dir}")
    print(
        f"[INFO] CONFIRMED={int((result_df['Status'] == 'CONFIRMED').sum())} "
        f"WATCH={int((result_df['Status'] == 'WATCH').sum())} "
        f"REJECTED={int((result_df['Status'] == 'REJECTED').sum())}"
    )
    if not candidates.empty:
        cols = [
            "Ticker",
            "Name",
            "Status",
            "Score",
            "Timing_Score",
            "Primary_Signal",
            "Close",
            "Long_MA_Slope_Pct",
            "Cross_Count",
            "Chase_Risk",
        ]
        print(candidates[cols].head(args.print_top).to_string(index=False))
    return 0


def explain(args) -> int:
    cfg = DEFAULT_CONFIG
    universe_df = TickerUniverse(args.info_excel).load()
    match = universe_df[universe_df["Ticker"].astype(str).str.zfill(6) == args.ticker.zfill(6)]
    if match.empty:
        name = args.ticker.zfill(6)
        market = ""
    else:
        name = str(match.iloc[0]["Name"])
        market = str(match.iloc[0]["Market"])

    provider = PykrxDataProvider(use_cache=not args.no_cache)
    df = provider.get_ohlcv(args.ticker.zfill(6), _history_start(args.date), args.date)
    if df.empty:
        print("[ERROR] OHLCV 없음")
        return 1

    result = MAChartSignalAnalyzer(cfg).analyze(
        args.ticker.zfill(6), name, market, args.date, df
    )
    print(pd.Series(result.to_row()).to_string())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="200MA direction + short-MA timing BUY analyzer")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--info-excel", default=str(DEFAULT_INFO_EXCEL))
    common.add_argument("--no-cache", action="store_true")

    s = sub.add_parser("scan", parents=[common])
    s.add_argument("--date", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    s.add_argument("--top-n", type=int, default=0, help="0=Universe 전체")
    s.add_argument(
        "--sort-by",
        default="market_cap",
        choices=["market_cap", "trading_value", "volume"],
    )
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
