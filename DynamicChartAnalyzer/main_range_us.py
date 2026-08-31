from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dynamic_chart_analyzer import DynamicChartAnalyzer, StrategyConfig
from main_range import _add_forward_metrics, _build_summary, parse_date_range
from us_market.provider import USYFinanceProvider
from us_market.universe import USUniverseService

HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="DynamicChartAnalyzer US market-cap TOP N range backtest")
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--universe-csv", required=True)
    p.add_argument("--top-n", type=int, default=300)
    p.add_argument("--forward-bars", type=int, default=60)
    p.add_argument("--history-days", type=int, default=450)
    p.add_argument("--capital", type=float, default=10_000_000)
    p.add_argument("--risk-cap", action="store_true")
    p.add_argument("--no-stop", action="store_true")
    p.add_argument("--dynamic-rsi", action="store_true")
    p.add_argument("--request-delay", type=float, default=0.02)
    p.add_argument("--output-root", default=str(HERE / "results_us"))
    return p.parse_args()


def _write_excel(
    path: Path,
    events: pd.DataFrame,
    confirmed: pd.DataFrame,
    summary: pd.DataFrame,
    universe: pd.DataFrame,
    errors: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        confirmed.to_excel(writer, sheet_name="ConfirmedStage3", index=False)
        events.to_excel(writer, sheet_name="AllEntryEvents", index=False)
        universe.to_excel(writer, sheet_name="Universe", index=False)
        errors.to_excel(writer, sheet_name="Errors", index=False)


def main() -> int:
    args = parse_args()
    start, end = parse_date_range(args.date_range)
    universe_service = USUniverseService(args.universe_csv)
    universe_info = universe_service.get_universe(
        top_n=args.top_n, sort_by="market_cap", include_etf=False
    )
    universe_df = universe_service.load_universe_df().head(args.top_n).copy()

    provider = USYFinanceProvider()
    cfg = StrategyConfig(
        total_capital=args.capital,
        use_two_percent_risk_cap=args.risk_cap,
        use_protective_stop=not args.no_stop,
    )
    analyzer = DynamicChartAnalyzer(cfg, include_dynamic_rsi=args.dynamic_rsi)

    history_start = (start - pd.Timedelta(days=args.history_days)).strftime("%Y-%m-%d")
    forward_end = (end + pd.Timedelta(days=max(120, args.forward_bars * 3))).strftime("%Y-%m-%d")

    print("=" * 78)
    print("DynamicChartAnalyzer US Range Backtest - fixed 1:2:7")
    print("=" * 78)
    print(f"Date range   : {start:%Y%m%d}~{end:%Y%m%d}")
    print(f"Universe     : CURRENT US market-cap TOP {len(universe_info)}")
    print(f"Forward bars : {args.forward_bars}")
    print("CONFIRMED    : LONG_ENTRY_STAGE_3 only")
    print("[WARNING] Current TOP N snapshot is reused historically; not PIT membership.")
    print()

    event_rows: list[dict] = []
    error_rows: list[dict] = []
    cap_map = {x.ticker: x.market_cap for x in universe_info}

    for idx, info in enumerate(universe_info, start=1):
        try:
            raw = provider.get_ohlcv(info.ticker, history_start, forward_end)
            analyzed, events = analyzer.analyze(raw)
            if events.empty:
                continue
            e = events.copy()
            e["date"] = pd.to_datetime(e["date"])
            e = e[(e["date"] >= start) & (e["date"] <= end)]
            e = e[e["action"].astype(str).str.contains("_ENTRY_STAGE_", regex=False)]
            if e.empty:
                continue

            for _, row in e.iterrows():
                action = str(row["action"])
                side = "SHORT" if action.startswith("SHORT_") else "LONG"
                direction = -1 if side == "SHORT" else 1
                base = {
                    "signal_date": pd.Timestamp(row["date"]),
                    "ticker": info.ticker,
                    "name": info.name,
                    "market": "US",
                    "market_cap": info.market_cap,
                    "source_rank": int(info.source_rank or idx),
                    "sort_by": "market_cap",
                    "side": side,
                    "direction": direction,
                    "stage": int(row.get("stage", 0)),
                    "action": action,
                    "entry_price": float(row["price"]),
                    "entry_amount_krw": float(row.get("amount_krw", np.nan)),
                    "cumulative_invested_krw": float(row.get("cumulative_invested_krw", np.nan)),
                    "weighted_entry_price": float(row.get("weighted_entry_price", np.nan)),
                    "stop_price": row.get("stop_price", np.nan),
                    "reference_target_price": row.get("reference_target_price", np.nan),
                    "risk_capped": bool(row.get("risk_capped", False)),
                }
                event_rows.append(_add_forward_metrics(base, analyzed, args.forward_bars))
        except Exception as exc:
            error_rows.append({"Ticker": info.ticker, "Name": info.name, "Error": repr(exc)})
            print(f"[WARN] {info.ticker} {info.name}: {exc}")
        if idx % 25 == 0 or idx == len(universe_info):
            print(f"[INFO] progress {idx}/{len(universe_info)} events={len(event_rows)}")
        time.sleep(max(0.0, float(args.request_delay)))

    events_df = pd.DataFrame(event_rows)
    if not events_df.empty:
        events_df = events_df.sort_values(["signal_date", "ticker", "stage"]).reset_index(drop=True)
        events_df["daily_stage_rank"] = (
            events_df.groupby(["signal_date", "side", "stage"])["source_rank"]
            .rank(method="first")
            .astype(int)
        )

    summary_df = _build_summary(events_df, args.forward_bars)
    errors_df = pd.DataFrame(error_rows, columns=["Ticker", "Name", "Error"])

    if events_df.empty:
        confirmed = pd.DataFrame()
    else:
        confirmed = events_df[(events_df["side"].eq("LONG")) & (events_df["stage"].eq(3))].copy()

    if confirmed.empty:
        candidate_columns = [
            "Actual_Date", "Ticker", "Name", "Market", "Status", "Primary_Signal",
            "Close", "Position_Stage", "Source_Rank", "Market_Cap",
        ]
        range_candidates = pd.DataFrame(columns=candidate_columns)
    else:
        range_candidates = confirmed.copy()
        range_candidates["Actual_Date"] = pd.to_datetime(range_candidates["signal_date"]).dt.strftime("%Y-%m-%d")
        range_candidates["Ticker"] = range_candidates["ticker"]
        range_candidates["Name"] = range_candidates["name"]
        range_candidates["Market"] = "US"
        range_candidates["Status"] = "CONFIRMED"
        range_candidates["Primary_Signal"] = range_candidates["action"]
        range_candidates["Close"] = range_candidates["entry_price"]
        range_candidates["Position_Stage"] = range_candidates["stage"]
        range_candidates["Source_Rank"] = range_candidates["source_rank"]
        range_candidates["Market_Cap"] = range_candidates["ticker"].map(cap_map)
        first = [
            "Actual_Date", "Ticker", "Name", "Market", "Status", "Primary_Signal",
            "Close", "Position_Stage", "Source_Rank", "Market_Cap",
        ]
        rest = [c for c in range_candidates.columns if c not in first]
        range_candidates = range_candidates[first + rest]

    out_dir = Path(args.output_root) / f"range_{start:%Y%m%d}_{end:%Y%m%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "dynamic_range_events.csv"
    summary_path = out_dir / "dynamic_range_summary.csv"
    candidates_path = out_dir / "range_candidates.csv"
    universe_path = out_dir / "universe.csv"
    errors_path = out_dir / "errors.csv"
    excel_path = out_dir / "dynamic_range_backtest.xlsx"

    events_df.to_csv(events_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    range_candidates.to_csv(candidates_path, index=False, encoding="utf-8-sig")
    universe_df.to_csv(universe_path, index=False, encoding="utf-8-sig")
    errors_df.to_csv(errors_path, index=False, encoding="utf-8-sig")
    _write_excel(excel_path, events_df, range_candidates, summary_df, universe_df, errors_df)

    print()
    print("=" * 78)
    print("Dynamic US range backtest finished")
    print("=" * 78)
    print(f"All entry events      : {len(events_df):,}")
    print(f"LONG Stage3 confirmed : {len(range_candidates):,}")
    print(f"Errors                : {len(errors_df):,}")
    print(f"Saved                 : {candidates_path}")
    print(f"Saved                 : {excel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
