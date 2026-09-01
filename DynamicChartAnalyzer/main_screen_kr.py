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
if str(KJB_ROOT) not in sys.path:
    sys.path.insert(0, str(KJB_ROOT))

from chartsel.universe.ticker_universe_service import TickerUniverseService  # noqa: E402
from dynamic_chart_analyzer import DynamicChartAnalyzer, StrategyConfig  # noqa: E402
from dynamic_chart_analyzer.providers import load_pykrx  # noqa: E402


def _classify(position_status: str) -> str:
    status = str(position_status or "").upper()
    if status == "LONG_CONFIRMED":
        return "CONFIRMED"
    if status in {"LONG_EARLY", "LONG_CONFIRMING"}:
        return "WATCH"
    return "REJECTED"


def _primary_signal(position_status: str, bar_actions: str) -> str:
    actions = str(bar_actions or "").strip()
    if actions:
        return actions
    status = str(position_status or "FLAT").upper()
    return {
        "LONG_CONFIRMED": "LONG_STAGE_3_ACTIVE",
        "LONG_CONFIRMING": "LONG_STAGE_2_ACTIVE",
        "LONG_EARLY": "LONG_STAGE_1_ACTIVE",
        "SHORT_CONFIRMED": "SHORT_STAGE_3_ACTIVE",
        "SHORT_CONFIRMING": "SHORT_STAGE_2_ACTIVE",
        "SHORT_EARLY": "SHORT_STAGE_1_ACTIVE",
    }.get(status, "FLAT")


def parse_args() -> argparse.Namespace:
    default_excel = os.environ.get("LIQUIDITY_UNIVERSE_XLSX", str(KJB_ROOT / "KOSPI_Info.xlsx"))
    p = argparse.ArgumentParser(description="DynamicChartAnalyzer KR trading-value TOP N screen")
    p.add_argument("--info-excel", default=default_excel)
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--sort-by", choices=["market_cap", "trading_value", "volume"], default="trading_value")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--capital", type=float, default=10_000_000)
    p.add_argument("--risk-cap", action="store_true")
    p.add_argument("--no-stop", action="store_true")
    p.add_argument("--dynamic-rsi", action="store_true")
    p.add_argument("--request-delay", type=float, default=0.02)
    p.add_argument("--output-root", default=str(HERE / "results"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    universe = TickerUniverseService(args.info_excel).get_universe(
        top_n=args.top_n,
        sort_by=args.sort_by,
        include_etf=False,
    )
    if not universe:
        print("[ERROR] Dynamic KR universe is empty.")
        return 1

    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=max(1, int(args.years))) - pd.Timedelta(days=30)
    cfg = StrategyConfig(
        total_capital=args.capital,
        use_two_percent_risk_cap=args.risk_cap,
        use_protective_stop=not args.no_stop,
    )
    analyzer = DynamicChartAnalyzer(cfg, include_dynamic_rsi=args.dynamic_rsi)

    print("=" * 78)
    print("DynamicChartAnalyzer KR Screening - fixed 1:2:7")
    print("=" * 78)
    print(f"Universe : recent liquidity TOP {len(universe)}")
    print(f"Sort by  : {args.sort_by}")
    print(f"History  : about {args.years} years")
    print("CONFIRMED: latest state == LONG_CONFIRMED (Stage 3 reached and still active)")
    print()

    rows: list[dict] = []
    errors: list[dict] = []
    for idx, info in enumerate(universe, start=1):
        try:
            raw = load_pykrx(info.ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            analyzed, _events = analyzer.analyze(raw)
            if analyzed.empty:
                raise ValueError("No analyzed rows")
            last = analyzed.iloc[-1]
            actual_date = pd.Timestamp(analyzed.index[-1]).strftime("%Y-%m-%d")
            position_status = str(last.get("position_status", "FLAT"))
            status = _classify(position_status)
            rows.append(
                {
                    "Actual_Date": actual_date,
                    "Ticker": info.ticker,
                    "Name": info.name,
                    "Market": info.market,
                    "Status": status,
                    "Position_Status": position_status,
                    "Position_Stage": int(last.get("position_stage", 0)),
                    "Position_Side": str(last.get("position_side", "")),
                    "Primary_Signal": _primary_signal(position_status, last.get("bar_actions", "")),
                    "Close": float(last["close"]),
                    "RSI": last.get("rsi"),
                    "MACD": last.get("macd"),
                    "Stop_Price": last.get("position_stop_price"),
                    "Reference_Target_Price": last.get("reference_target_price"),
                    "Planned_Next_Entry": last.get("planned_next_entry_krw"),
                    "Trading_Value": info.trading_value,
                    "Market_Cap": info.market_cap,
                    "Source_Rank": info.source_rank,
                }
            )
            if idx % 25 == 0 or idx == len(universe):
                print(f"[INFO] progress {idx}/{len(universe)}")
        except Exception as exc:
            errors.append({"Ticker": info.ticker, "Name": info.name, "Error": repr(exc)})
            print(f"[WARN] {info.ticker} {info.name}: {exc}")
        time.sleep(max(0.0, float(args.request_delay)))

    if not rows:
        print("[ERROR] Dynamic KR screening produced no rows.")
        return 1

    result = pd.DataFrame(rows)
    status_rank = {"CONFIRMED": 0, "WATCH": 1, "REJECTED": 2}
    result["_rank"] = result["Status"].map(status_rank).fillna(9)
    result = result.sort_values(
        ["_rank", "Position_Stage", "Source_Rank"],
        ascending=[True, False, True],
    ).drop(columns="_rank").reset_index(drop=True)
    candidates = result[result["Status"].isin({"CONFIRMED", "WATCH"})].copy()
    confirmed = result[result["Status"].eq("CONFIRMED")].copy()

    latest_date = pd.to_datetime(result["Actual_Date"], errors="coerce").max()
    dir_key = latest_date.strftime("%Y%m%d") if pd.notna(latest_date) else end.strftime("%Y%m%d")
    out_dir = Path(args.output_root) / dir_key
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / "scan_results.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(out_dir / "candidates.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(errors, columns=["Ticker", "Name", "Error"]).to_csv(
        out_dir / "errors.csv", index=False, encoding="utf-8-sig"
    )

    with pd.ExcelWriter(out_dir / "dynamic_candidates.xlsx", engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="AllResults", index=False)
        candidates.to_excel(writer, sheet_name="Candidates", index=False)
        confirmed.to_excel(writer, sheet_name="Confirmed", index=False)
        pd.DataFrame(errors, columns=["Ticker", "Name", "Error"]).to_excel(
            writer, sheet_name="Errors", index=False
        )

    counts = result["Status"].value_counts()
    print()
    print(f"[DONE] {out_dir}")
    print(
        f"[INFO] CONFIRMED={int(counts.get('CONFIRMED', 0))} "
        f"WATCH={int(counts.get('WATCH', 0))} REJECTED={int(counts.get('REJECTED', 0))}"
    )
    if not confirmed.empty:
        print(
            confirmed[["Ticker", "Name", "Status", "Position_Status", "Close", "Source_Rank"]]
            .head(30)
            .to_string(index=False)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
