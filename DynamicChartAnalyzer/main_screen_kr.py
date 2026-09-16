from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KJB_ROOT = ROOT / "KJBChartAnalyzer"
if str(KJB_ROOT) not in sys.path:
    sys.path.insert(0, str(KJB_ROOT))

from chartsel.universe.ticker_universe_service import TickerUniverseService  # noqa: E402
from dynamic_chart_analyzer import DynamicChartAnalyzer, StrategyConfig  # noqa: E402
from dynamic_chart_analyzer.long_v2 import (  # noqa: E402
    BASE_EVENT_FEATURE_COLUMNS,
    add_long_v2_features,
    add_rs_percentiles,
    prepare_market_features,
)
from dynamic_chart_analyzer.long_v23 import score_long_events  # noqa: E402
from dynamic_chart_analyzer.providers import load_pykrx  # noqa: E402


MARKET_PROXY = {
    "KOSPI": "1001",
    "KOSDAQ": "2001",
}
LONG_POSITION_STATUSES = {"LONG_EARLY", "LONG_CONFIRMING", "LONG_CONFIRMED"}
LONG_ENTRY_PREFIX = "LONG_ENTRY_STAGE_"


def _status_from_quality(side: str, label: str) -> str:
    if str(side).upper() != "LONG":
        return "REJECTED"
    text = str(label or "").upper()
    if text == "CONFIRMED":
        return "CONFIRMED"
    if text == "WATCH":
        return "WATCH"
    return "REJECTED"


def _action_list(bar_actions: str) -> list[str]:
    return [part.strip() for part in str(bar_actions or "").split("|") if part.strip()]


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


def _signal_type(position_status: str, bar_actions: str) -> str:
    """Separate today's new entry event from a previously-open position.

    NEW means a LONG_ENTRY_STAGE_n event happened on the latest bar. ACTIVE means
    the state machine still holds a LONG position but there was no new entry today.
    ACTIVE rows are monitoring rows and must not be counted as fresh recommendations.
    """
    status = str(position_status or "FLAT").upper()
    actions = _action_list(bar_actions)
    if status in LONG_POSITION_STATUSES and any(action.startswith(LONG_ENTRY_PREFIX) for action in actions):
        return "NEW"
    if status in LONG_POSITION_STATUSES:
        return "ACTIVE"
    return "NONE"


def _position_setup_metadata(
    ticker: str,
    analyzed: pd.DataFrame,
    events: pd.DataFrame,
    position_status: str,
    stage: int,
) -> dict[str, object]:
    """Return stable metadata for the currently-open LONG setup.

    setup_id uses ticker + the latest Stage-1 entry date. A Stage-1 entry uniquely
    opens a setup in this state machine, so the ID remains stable while Stage2/3
    progress and while the position remains ACTIVE on later scan dates.
    """
    empty = {
        "setup_id": "",
        "setup_start_date": pd.NaT,
        "stage_entry_date": pd.NaT,
        "days_in_stage": np.nan,
    }
    if str(position_status or "").upper() not in LONG_POSITION_STATUSES or stage <= 0:
        return empty
    if events is None or events.empty:
        return empty

    e = events.copy()
    if "date" not in e.columns or "action" not in e.columns:
        return empty
    e["date"] = pd.to_datetime(e["date"], errors="coerce")
    e["action"] = e["action"].astype(str)
    e = e[e["date"].notna()].sort_values("date", kind="stable")

    stage1 = e[e["action"].eq("LONG_ENTRY_STAGE_1")]
    if stage1.empty:
        return empty

    setup_start = pd.Timestamp(stage1.iloc[-1]["date"]).normalize()
    stamp = setup_start.strftime("%Y%m%d")
    setup_id = f"{str(ticker).zfill(6)}_{stamp}"

    current_stage_entries = e[
        e["action"].eq(f"LONG_ENTRY_STAGE_{int(stage)}") & e["date"].ge(setup_start)
    ]
    stage_entry = (
        pd.Timestamp(current_stage_entries.iloc[-1]["date"]).normalize()
        if not current_stage_entries.empty
        else setup_start
    )

    days_in_stage = np.nan
    if analyzed is not None and not analyzed.empty:
        idx = pd.to_datetime(analyzed.index, errors="coerce")
        valid = idx.notna() & (idx.normalize() >= stage_entry)
        if valid.any():
            # Trading bars elapsed: entry day=0, next trading day=1, ...
            days_in_stage = max(0, int(valid.sum()) - 1)

    return {
        "setup_id": setup_id,
        "setup_start_date": setup_start,
        "stage_entry_date": stage_entry,
        "days_in_stage": days_in_stage,
    }


def _load_market_feature_map(markets: set[str], start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.DataFrame]:
    feature_map: dict[str, pd.DataFrame] = {}
    for market in sorted(markets):
        proxy = MARKET_PROXY.get(market)
        if not proxy:
            continue
        try:
            raw = load_pykrx(proxy, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            feature_map[market] = prepare_market_features(raw)
            print(f"[QUALITY] Market proxy {market}: index {proxy} ({len(raw):,} bars)")
        except Exception as exc:
            print(f"[WARN] Market proxy failed {market}/{proxy}: {exc}")
    return feature_map


def _scalar(value):
    if isinstance(value, pd.Series):
        if value.empty:
            return np.nan
        value = value.iloc[-1]
    if value is pd.NA:
        return np.nan
    return value


def parse_args() -> argparse.Namespace:
    default_excel = os.environ.get("LIQUIDITY_UNIVERSE_XLSX", str(KJB_ROOT / "KOSPI_Info.xlsx"))
    p = argparse.ArgumentParser(
        description="DynamicChartAnalyzer KR screen using V2.3 quality and NEW/ACTIVE separation"
    )
    p.add_argument("--info-excel", default=default_excel)
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--sort-by", choices=["market_cap", "trading_value", "volume"], default="trading_value")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--capital", type=float, default=10_000_000)
    p.add_argument("--risk-cap", action="store_true")
    p.add_argument("--no-stop", action="store_true")
    p.add_argument("--dynamic-rsi", action="store_true")
    p.add_argument("--confirmed-score", type=float, default=70.0)
    p.add_argument("--watch-score", type=float, default=55.0)
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
    markets = {str(info.market or "").upper() for info in universe}
    market_feature_map = _load_market_feature_map(markets, start, end)

    print("=" * 78)
    print("DynamicChartAnalyzer KR Screening - V2.3 Stage-aware Quality")
    print("=" * 78)
    print(f"Universe : recent liquidity TOP {len(universe)}")
    print(f"Sort by  : {args.sort_by}")
    print(f"History  : about {args.years} years")
    print(f"CONFIRMED: V2.3 stage_quality_score >= {args.confirmed_score:g}")
    print(f"WATCH    : V2.3 stage_quality_score >= {args.watch_score:g}")
    print("NEW      : a LONG_ENTRY_STAGE_n event occurred on the latest bar")
    print("ACTIVE   : an earlier LONG setup is still open; monitoring only, not a fresh recommendation")
    print(
        "Stage timing/allocation: RSI -> MACD -> Ichimoku, "
        f"{cfg.stage1_ratio:.0%}:{cfg.stage2_ratio:.0%}:{cfg.stage3_ratio:.0%} (2:6:2 experiment)"
    )
    print()

    rows: list[dict] = []
    errors: list[dict] = []
    for idx, info in enumerate(universe, start=1):
        try:
            raw = load_pykrx(info.ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            analyzed, events = analyzer.analyze(raw)
            if analyzed.empty:
                raise ValueError("No analyzed rows")
            market = str(info.market or "").upper()
            enriched = add_long_v2_features(analyzed, market_feature_map.get(market))
            last = enriched.iloc[-1]
            actual_date = pd.Timestamp(enriched.index[-1]).normalize()
            position_status = str(last.get("position_status", "FLAT")).upper()
            stage_value = pd.to_numeric(pd.Series([last.get("position_stage", 0)]), errors="coerce").iloc[0]
            stage = int(stage_value) if pd.notna(stage_value) else 0
            side = "LONG" if position_status in LONG_POSITION_STATUSES else "OTHER"
            bar_actions = str(last.get("bar_actions", "") or "")
            primary_signal = _primary_signal(position_status, bar_actions)
            signal_type = _signal_type(position_status, bar_actions)
            setup_meta = _position_setup_metadata(
                str(info.ticker).zfill(6), analyzed, events, position_status, stage
            )

            row = {
                "signal_date": actual_date,
                "ticker": info.ticker,
                "name": info.name,
                "market": market,
                "source_rank": info.source_rank,
                "sort_by": args.sort_by,
                "side": side,
                "direction": 1,
                "stage": stage,
                "action": primary_signal,
                "entry_price": float(last["close"]),
                "Position_Status": position_status,
                "Position_Stage": stage,
                "Position_Side": str(last.get("position_side", "")),
                "Primary_Signal": primary_signal,
                "Bar_Actions": bar_actions,
                "Signal_Type": signal_type,
                "Is_New_Signal": signal_type == "NEW",
                "Is_Active_Position": signal_type == "ACTIVE",
                "Close": float(last["close"]),
                "Stop_Price": last.get("position_stop_price"),
                "Reference_Target_Price": last.get("reference_target_price"),
                "Planned_Next_Entry": last.get("planned_next_entry_krw"),
                "Trading_Value": info.trading_value,
                "Market_Cap": info.market_cap,
                "Source_Rank": info.source_rank,
                **setup_meta,
            }
            for col in BASE_EVENT_FEATURE_COLUMNS:
                row[col] = _scalar(last.get(col, np.nan))
            rows.append(row)
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
    result = add_rs_percentiles(result)

    # V2.3 computes stage-specific quality on the current bar. It also creates its
    # own range-oriented setup fields, so preserve the screen's state-derived setup
    # metadata and restore it after scoring.
    screen_setup = result[["setup_id", "setup_start_date", "stage_entry_date", "days_in_stage"]].copy()
    result = score_long_events(
        result,
        confirmed_score=float(args.confirmed_score),
        watch_score=float(args.watch_score),
    )
    for col in screen_setup.columns:
        result[col] = screen_setup[col].to_numpy()

    result["Status"] = [
        _status_from_quality(side, label)
        for side, label in zip(result["side"], result["long_quality_label"])
    ]
    result["Is_Recommendation_Event"] = (
        result["Signal_Type"].eq("NEW") & result["Status"].isin({"CONFIRMED", "WATCH"})
    )
    result["Actual_Date"] = pd.to_datetime(result["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["Setup_Start_Date"] = pd.to_datetime(result["setup_start_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["Stage_Entry_Date"] = pd.to_datetime(result["stage_entry_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["Ticker"] = result["ticker"].astype(str).str.zfill(6)
    result["Name"] = result["name"]
    result["Market"] = result["market"]
    result["Score"] = pd.to_numeric(result.get("stage_quality_score"), errors="coerce")
    result["Timing_Score"] = pd.to_numeric(result.get("lecture_score"), errors="coerce")
    result["Quality_Score"] = result["Score"]
    result["Lecture_Score"] = result["Timing_Score"]
    result["Quality_Label"] = result["stage_quality_label"].replace({"REJECT": "REJECTED"})

    status_rank = {"CONFIRMED": 0, "WATCH": 1, "REJECTED": 2}
    signal_rank = {"NEW": 0, "ACTIVE": 1, "NONE": 2}
    result["_status_rank"] = result["Status"].map(status_rank).fillna(9)
    result["_signal_rank"] = result["Signal_Type"].map(signal_rank).fillna(9)
    result = result.sort_values(
        ["_signal_rank", "_status_rank", "Score", "Timing_Score", "Source_Rank"],
        ascending=[True, True, False, False, True],
        na_position="last",
    ).drop(columns=["_status_rank", "_signal_rank"]).reset_index(drop=True)

    qualified = result[result["Status"].isin({"CONFIRMED", "WATCH"})].copy()
    new_candidates = qualified[qualified["Signal_Type"].eq("NEW")].copy()
    confirmed = new_candidates[new_candidates["Status"].eq("CONFIRMED")].copy()
    stage2_confirmed = confirmed[confirmed["Position_Stage"].eq(2)].copy()
    stage3_confirmed = confirmed[confirmed["Position_Stage"].eq(3)].copy()
    final_confirmed = confirmed[confirmed["Position_Stage"].isin([2, 3])].copy()
    if not final_confirmed.empty:
        final_confirmed = final_confirmed.sort_values(
            ["Position_Stage", "Score", "Timing_Score", "Source_Rank"],
            ascending=[False, False, False, True],
            na_position="last",
        )
    active_positions = result[result["Signal_Type"].eq("ACTIVE") & result["side"].eq("LONG")].copy()

    latest_date = pd.to_datetime(result["Actual_Date"], errors="coerce").max()
    dir_key = latest_date.strftime("%Y%m%d") if pd.notna(latest_date) else end.strftime("%Y%m%d")
    out_dir = Path(args.output_root) / dir_key
    out_dir.mkdir(parents=True, exist_ok=True)

    result.to_csv(out_dir / "scan_results.csv", index=False, encoding="utf-8-sig")
    # Backward-compatible downstream path now intentionally contains fresh signals only.
    new_candidates.to_csv(out_dir / "candidates.csv", index=False, encoding="utf-8-sig")
    new_candidates.to_csv(out_dir / "new_candidates.csv", index=False, encoding="utf-8-sig")
    confirmed.to_csv(out_dir / "confirmed_candidates.csv", index=False, encoding="utf-8-sig")
    final_confirmed.to_csv(out_dir / "final_confirmed_candidates.csv", index=False, encoding="utf-8-sig")
    stage2_confirmed.to_csv(out_dir / "stage2_confirmed_candidates.csv", index=False, encoding="utf-8-sig")
    stage3_confirmed.to_csv(out_dir / "stage3_confirmed_candidates.csv", index=False, encoding="utf-8-sig")
    active_positions.to_csv(out_dir / "active_positions.csv", index=False, encoding="utf-8-sig")
    qualified.to_csv(out_dir / "all_qualified.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(errors, columns=["Ticker", "Name", "Error"]).to_csv(
        out_dir / "errors.csv", index=False, encoding="utf-8-sig"
    )

    with pd.ExcelWriter(out_dir / "dynamic_candidates.xlsx", engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="AllResults", index=False)
        new_candidates.to_excel(writer, sheet_name="NewCandidates", index=False)
        confirmed.to_excel(writer, sheet_name="Confirmed", index=False)
        final_confirmed.to_excel(writer, sheet_name="FinalConfirmed", index=False)
        stage2_confirmed.to_excel(writer, sheet_name="Stage2Confirmed", index=False)
        stage3_confirmed.to_excel(writer, sheet_name="Stage3Confirmed", index=False)
        active_positions.to_excel(writer, sheet_name="ActivePositions", index=False)
        qualified.to_excel(writer, sheet_name="AllQualified", index=False)
        pd.DataFrame(errors, columns=["Ticker", "Name", "Error"]).to_excel(
            writer, sheet_name="Errors", index=False
        )

    new_counts = new_candidates["Status"].value_counts()
    active_counts = active_positions["Status"].value_counts()
    print()
    print(f"[DONE] {out_dir}")
    print(
        f"[INFO] NEW CONFIRMED={int(new_counts.get('CONFIRMED', 0))} "
        f"NEW WATCH={int(new_counts.get('WATCH', 0))} "
        f"ACTIVE={len(active_positions)}"
    )
    print(
        f"[INFO] FINAL CONFIRMED Stage2={len(stage2_confirmed)} "
        f"Stage3={len(stage3_confirmed)} Total={len(final_confirmed)}"
    )
    print(
        f"[INFO] ACTIVE quality: CONFIRMED={int(active_counts.get('CONFIRMED', 0))} "
        f"WATCH={int(active_counts.get('WATCH', 0))} "
        f"REJECTED={int(active_counts.get('REJECTED', 0))}"
    )
    if not final_confirmed.empty:
        cols = [
            "Ticker", "Name", "Position_Stage", "Signal_Type", "Status", "Quality_Score", "Lecture_Score",
            "Position_Status", "Primary_Signal", "setup_id", "Stage_Entry_Date", "days_in_stage", "Close",
        ]
        print("\n[FINAL CONFIRMED - STAGE 2 + STAGE 3]")
        print(final_confirmed[cols].head(30).to_string(index=False))
    if not active_positions.empty:
        cols = [
            "Ticker", "Name", "Status", "Quality_Score", "Position_Status",
            "setup_id", "Stage_Entry_Date", "days_in_stage", "Close",
        ]
        print("\n[ACTIVE POSITIONS - monitoring only]")
        print(active_positions[cols].head(30).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
