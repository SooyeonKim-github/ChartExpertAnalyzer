from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KJB_ROOT = ROOT / "KJBChartAnalyzer"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(KJB_ROOT) not in sys.path:
    sys.path.insert(0, str(KJB_ROOT))

from scripts.build_liquidity_universe import build_liquidity_universe  # noqa: E402
from chartsel.data.pykrx_provider import PykrxDataProvider  # noqa: E402
from chartsel.sector.sector_service import SectorBacktestService  # noqa: E402

from CloseBetAnalyzer.analyzer import CloseBetAnalyzer  # noqa: E402
from CloseBetAnalyzer.config import DEFAULT_CONFIG  # noqa: E402


HORIZONS = (1, 5, 10, 20, 40, 60)
CONFIRMED_STATUSES = {"STRONG_CONFIRMED", "CONFIRMED"}
CANDIDATE_STATUSES = {"STRONG_CONFIRMED", "CONFIRMED", "WATCH"}


def _parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    raw = str(text or "").strip().replace(" ", "")
    if "~" not in raw:
        raise ValueError("--date-range must be YYYYMMDD~YYYYMMDD")
    left, right = raw.split("~", 1)
    start = pd.to_datetime(left, format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(right, format="%Y%m%d", errors="raise").normalize()
    if start > end:
        raise ValueError(f"start date is after end date: {start.date()} > {end.date()}")
    return start, end


def _market_key(market: str) -> str:
    return "^KQ11" if "KOSDAQ" in str(market).upper() else "^KS11"


def _ticker(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _performance_metrics(full_df: pd.DataFrame, entry_date: pd.Timestamp, entry_close: float) -> dict:
    out: dict[str, float | str] = {
        "entry_date": entry_date.strftime("%Y-%m-%d"),
        "entry_close": float(entry_close),
    }
    future = full_df.loc[full_df.index > entry_date].copy()
    if future.empty or entry_close <= 0:
        out["D+1_Open_Return_Pct"] = np.nan
        for h in HORIZONS:
            out[f"D+{h}_Close_Return_Pct"] = np.nan
            out[f"MFE_{h}D_Pct"] = np.nan
            out[f"MAE_{h}D_Pct"] = np.nan
        return out

    out["D+1_Open_Return_Pct"] = (float(future.iloc[0]["Open"]) / entry_close - 1.0) * 100.0
    for h in HORIZONS:
        if len(future) < h:
            out[f"D+{h}_Close_Return_Pct"] = np.nan
            out[f"MFE_{h}D_Pct"] = np.nan
            out[f"MAE_{h}D_Pct"] = np.nan
            continue
        window = future.iloc[:h]
        out[f"D+{h}_Close_Return_Pct"] = (float(window.iloc[-1]["Close"]) / entry_close - 1.0) * 100.0
        out[f"MFE_{h}D_Pct"] = (float(pd.to_numeric(window["High"], errors="coerce").max()) / entry_close - 1.0) * 100.0
        out[f"MAE_{h}D_Pct"] = (float(pd.to_numeric(window["Low"], errors="coerce").min()) / entry_close - 1.0) * 100.0
    return out


def _buy_day_decision(guide, entry_close: float) -> tuple[str, str]:
    px = float(entry_close)
    if px <= float(guide.cancel_below):
        return "SKIP_CANCEL", "매수당일 종가가 취소선 이하"
    if px >= float(guide.chase_above):
        return "SKIP_CHASE", "매수당일 종가가 추격금지선 이상"
    if (
        px >= float(guide.preferred_low)
        and px <= float(guide.preferred_high)
        and px >= float(guide.hold_level)
    ):
        return "BUY", "매수당일 종가가 선호 범위/유지선 충족"
    if px < float(guide.hold_level):
        return "WAIT_WEAK", "취소선은 지켰지만 유지선 회복 부족"
    return "WAIT_EXTENDED", "추격금지선 전이지만 선호 상단 초과"


def _summary_for(frame: pd.DataFrame, cohort: str) -> list[dict]:
    rows: list[dict] = []
    for h in HORIZONS:
        col = f"D+{h}_Close_Return_Pct"
        values = pd.to_numeric(frame.get(col, pd.Series(dtype=float)), errors="coerce").dropna()
        mfe = pd.to_numeric(frame.get(f"MFE_{h}D_Pct", pd.Series(dtype=float)), errors="coerce").dropna()
        mae = pd.to_numeric(frame.get(f"MAE_{h}D_Pct", pd.Series(dtype=float)), errors="coerce").dropna()
        rows.append(
            {
                "cohort": cohort,
                "horizon": f"D+{h}",
                "signal_count": int(len(frame)),
                "complete_count": int(len(values)),
                "avg_return_pct": float(values.mean()) if len(values) else np.nan,
                "median_return_pct": float(values.median()) if len(values) else np.nan,
                "win_rate_pct": float((values > 0).mean() * 100.0) if len(values) else np.nan,
                "avg_mfe_pct": float(mfe.mean()) if len(mfe) else np.nan,
                "avg_mae_pct": float(mae.mean()) if len(mae) else np.nan,
            }
        )
    return rows


def _build_summary(performance: pd.DataFrame, selected: pd.DataFrame, daily_top_n: int) -> pd.DataFrame:
    rows: list[dict] = []
    rows.extend(_summary_for(performance, "ALL_EXECUTED_CONFIRMED"))
    rows.extend(_summary_for(selected, f"DAILY_TOP{daily_top_n}"))
    if not performance.empty and "status" in performance.columns:
        for status, group in performance.groupby("status"):
            rows.extend(_summary_for(group, str(status)))
    return pd.DataFrame(rows)


def _write_excel(path: Path, all_results: pd.DataFrame, candidates: pd.DataFrame, performance: pd.DataFrame, selected: pd.DataFrame, summary: pd.DataFrame, errors: pd.DataFrame) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        all_results.to_excel(writer, sheet_name="AllResults", index=False)
        candidates.to_excel(writer, sheet_name="Candidates", index=False)
        performance.to_excel(writer, sheet_name="ConfirmedPerformance", index=False)
        selected.to_excel(writer, sheet_name="DailySelected", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
        errors.to_excel(writer, sheet_name="Errors", index=False)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CloseBetAnalyzer V2 range backtest: T-1 selection -> T close entry")
    p.add_argument("--date-range", required=True, help="BUY dates, YYYYMMDD~YYYYMMDD")
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--lookback", type=int, default=20, help="liquidity universe rolling trading days")
    p.add_argument("--daily-top-n", type=int, default=5, help="executed confirmed names kept per buy date")
    p.add_argument("--forward-bars", type=int, default=60)
    p.add_argument("--history-days", type=int, default=520)
    p.add_argument("--request-delay", type=float, default=0.01)
    p.add_argument("--sector-info-excel", default=str(KJB_ROOT / "KOSPI_Info.xlsx"))
    p.add_argument("--output-root", default=str(HERE / "results"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    range_start, range_end = _parse_date_range(args.date_range)
    if args.top_n <= 0:
        raise ValueError("--top-n must be positive")
    if args.daily_top_n <= 0:
        raise ValueError("--daily-top-n must be positive")

    out_dir = Path(args.output_root) / f"range_{range_start:%Y%m%d}_{range_end:%Y%m%d}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 96)
    print("CloseBetAnalyzer V2 - Range Backtest")
    print("=" * 96)
    print(f"Buy-date range   : {range_start:%Y%m%d}~{range_end:%Y%m%d}")
    print(f"Universe         : point-in-time recent {args.lookback}-day avg trading value TOP {args.top_n}")
    print("Markets          : KOSPI + KOSDAQ")
    print("Candidate signal : T-1 completed daily data only")
    print("Buy-day check    : T close vs the T-1 price guide only (no T chart scoring)")
    print("Entry assumption : BUY guide passed -> T close")
    print(f"Daily selection  : executed confirmed score TOP {args.daily_top_n}")
    print(f"Forward bars     : {args.forward_bars}")
    print("=" * 96)

    universe_start = range_start - pd.Timedelta(days=14)
    print("[1/6] Building point-in-time liquidity universe...")
    membership_ext = build_liquidity_universe(
        universe_start,
        range_end,
        top_n=args.top_n,
        lookback=args.lookback,
        markets=("KOSPI", "KOSDAQ"),
        cache_dir=ROOT / "cache" / "liquidity_universe",
    )
    membership_ext["date"] = pd.to_datetime(membership_ext["date"]).dt.normalize()
    membership_ext["ticker"] = membership_ext["ticker"].map(_ticker)
    membership = membership_ext[(membership_ext["date"] >= range_start) & (membership_ext["date"] <= range_end)].copy()
    membership.to_csv(out_dir / "liquidity_universe_daily.csv", index=False, encoding="utf-8-sig")

    all_market_dates = sorted(pd.Timestamp(x).normalize() for x in membership_ext["date"].unique())
    buy_dates = [d for d in all_market_dates if range_start <= d <= range_end]
    if not buy_dates:
        print("[ERROR] no buy dates in requested range.")
        return 1

    member_groups = {pd.Timestamp(date).normalize(): group.sort_values("source_rank") for date, group in membership_ext.groupby("date")}
    signal_for_buy: dict[pd.Timestamp, pd.Timestamp] = {}
    for buy_date in buy_dates:
        prior = [d for d in all_market_dates if d < buy_date]
        if prior:
            signal_for_buy[buy_date] = prior[-1]

    signal_dates = sorted(set(signal_for_buy.values()))
    union_members = membership_ext[membership_ext["date"].isin(signal_dates)]
    union = union_members[["ticker", "name", "market"]].drop_duplicates("ticker", keep="last").sort_values("ticker").reset_index(drop=True)
    print(f"[INFO] buy_dates={len(buy_dates)} signal_dates={len(signal_dates)} union_tickers={len(union)}")

    provider = PykrxDataProvider(cache_dir=HERE / "cache" / "range", use_cache=True)
    analyzer = CloseBetAnalyzer(DEFAULT_CONFIG)
    warm_start = min(signal_dates) - pd.Timedelta(days=max(360, int(args.history_days)))
    future_end = range_end + pd.Timedelta(days=max(100, int(args.forward_bars) * 2 + 20))

    print("[2/6] Loading benchmark history...")
    benchmarks: dict[str, pd.DataFrame] = {}
    for key in ("^KS11", "^KQ11"):
        try:
            benchmarks[key] = provider.get_ohlcv_by_date(key, warm_start.strftime("%Y%m%d"), future_end.strftime("%Y%m%d"))
        except Exception as exc:
            print(f"[WARN] benchmark {key}: {exc}")
            benchmarks[key] = pd.DataFrame()

    print("[3/6] Loading union stock history...")
    price_cache: dict[str, pd.DataFrame] = {}
    errors: list[dict] = []
    for idx, row in union.iterrows():
        ticker = _ticker(row["ticker"])
        try:
            df = provider.get_ohlcv_by_date(ticker, warm_start.strftime("%Y%m%d"), future_end.strftime("%Y%m%d"))
            if df.empty:
                raise ValueError("empty OHLCV")
            price_cache[ticker] = df
        except Exception as exc:
            errors.append({"signal_date": "", "entry_date": "", "ticker": ticker, "name": row.get("name", ""), "stage": "LOAD", "error": repr(exc)})
        done = idx + 1
        if done == 1 or done % 25 == 0 or done == len(union):
            print(f"[INFO] price load {done}/{len(union)} ready={len(price_cache)}")
        time.sleep(max(0.0, float(args.request_delay)))

    print("[4/6] Building reusable sector context...")
    sector_service = None
    try:
        sector_price_cache = {ticker: df.loc[df.index <= max(signal_dates)].copy() for ticker, df in price_cache.items()}
        benchmark_to_signal_end = {key: df.loc[df.index <= max(signal_dates)].copy() for key, df in benchmarks.items()}
        sector_service = SectorBacktestService(args.sector_info_excel)
        sector_service.build(price_cache=sector_price_cache, benchmark_cache=benchmark_to_signal_end, allowed_tickers=set(sector_price_cache))
        print(f"[INFO] sector context ready scope={sector_service.aggregation_scope}")
        print("[INFO] unmapped/ETF-like sector labels are excluded from CloseBet score.")
    except Exception as exc:
        print(f"[WARN] sector context disabled: {exc}")
        sector_service = None

    print("[5/6] Replaying T-1 signal -> T buy day...")
    all_rows: list[dict] = []
    for date_no, buy_date in enumerate(buy_dates, start=1):
        signal_date = signal_for_buy.get(buy_date)
        if signal_date is None:
            continue
        day_members = member_groups.get(signal_date)
        if day_members is None or day_members.empty:
            continue
        day_result_count = 0

        for _, member in day_members.iterrows():
            ticker = _ticker(member["ticker"])
            full_df = price_cache.get(ticker)
            if full_df is None or full_df.empty:
                continue
            stock_history = full_df.loc[full_df.index <= signal_date].copy()
            if len(stock_history) < 130 or pd.Timestamp(stock_history.index[-1]).normalize() != signal_date:
                continue
            entry_rows = full_df.loc[full_df.index == buy_date]
            if entry_rows.empty:
                continue
            entry_close = float(entry_rows.iloc[-1]["Close"])

            market = str(member.get("market", "KOSPI")).upper()
            market_key = _market_key(market)
            full_market = benchmarks.get(market_key, pd.DataFrame())
            market_history = full_market.loc[full_market.index <= signal_date].copy()
            if len(market_history) < 130 or pd.Timestamp(market_history.index[-1]).normalize() != signal_date:
                continue

            try:
                sector_ctx = sector_service.context(ticker, signal_date, market) if sector_service is not None else None
                analyzed = analyzer.analyze(
                    ticker=ticker,
                    name=str(member.get("name", ticker)),
                    market=market,
                    stock_df=stock_history,
                    market_df=market_history,
                    sector_context=sector_ctx,
                    source_rank=int(member["source_rank"]),
                    universe_size=len(day_members),
                )
                row = analyzed.to_dict()
                row["signal_date"] = signal_date.strftime("%Y-%m-%d")
                row["entry_date"] = buy_date.strftime("%Y-%m-%d")
                row["universe_source_rank"] = int(member["source_rank"])
                row["universe_avg_trading_value_20d"] = member.get("avg_trading_value_20d", np.nan)
                row["universe_trading_value"] = member.get("trading_value", np.nan)

                decision, decision_reason = _buy_day_decision(analyzed.guide, entry_close)
                row["buy_day_decision"] = decision
                row["buy_day_decision_reason"] = decision_reason
                row["buy_day_close"] = entry_close
                row["buy_day_return_from_reference_pct"] = (entry_close / float(analyzed.guide.reference_close) - 1.0) * 100.0

                if analyzed.status in CONFIRMED_STATUSES and decision == "BUY":
                    row.update(_performance_metrics(full_df, buy_date, entry_close))
                else:
                    row["entry_close"] = np.nan
                    row["D+1_Open_Return_Pct"] = np.nan
                    for h in HORIZONS:
                        row[f"D+{h}_Close_Return_Pct"] = np.nan
                        row[f"MFE_{h}D_Pct"] = np.nan
                        row[f"MAE_{h}D_Pct"] = np.nan
                all_rows.append(row)
                day_result_count += 1
            except Exception as exc:
                errors.append({"signal_date": signal_date.strftime("%Y-%m-%d"), "entry_date": buy_date.strftime("%Y-%m-%d"), "ticker": ticker, "name": member.get("name", ""), "stage": "ANALYZE", "error": repr(exc)})

        if date_no == 1 or date_no % 10 == 0 or date_no == len(buy_dates):
            print(f"[INFO] replay {date_no}/{len(buy_dates)} signal={signal_date:%Y-%m-%d} buy={buy_date:%Y-%m-%d} results={day_result_count} total={len(all_rows)}")

    if not all_rows:
        print("[ERROR] no range results.")
        return 1

    print("[6/6] Writing performance outputs...")
    all_results = pd.DataFrame(all_rows)
    status_rank = {"STRONG_CONFIRMED": 0, "CONFIRMED": 1, "WATCH": 2, "REJECTED": 3}
    all_results["_status_rank"] = all_results["status"].map(status_rank).fillna(9)
    all_results = all_results.sort_values(["entry_date", "_status_rank", "score", "universe_source_rank", "ticker"], ascending=[True, True, False, True, True]).drop(columns="_status_rank").reset_index(drop=True)

    candidates = all_results[all_results["status"].isin(CANDIDATE_STATUSES)].copy()
    performance = all_results[all_results["status"].isin(CONFIRMED_STATUSES) & all_results["buy_day_decision"].eq("BUY")].copy()
    if performance.empty:
        selected = performance.copy()
    else:
        selected = performance.sort_values(["entry_date", "score", "stock_rs_score", "structure_score", "ticker"], ascending=[True, False, False, False, True]).groupby("entry_date", as_index=False, group_keys=False).head(args.daily_top_n).reset_index(drop=True)

    summary = _build_summary(performance, selected, args.daily_top_n)
    error_df = pd.DataFrame(errors, columns=["signal_date", "entry_date", "ticker", "name", "stage", "error"])

    all_results.to_csv(out_dir / "range_all_results.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(out_dir / "range_candidates.csv", index=False, encoding="utf-8-sig")
    performance.to_csv(out_dir / "range_confirmed_performance.csv", index=False, encoding="utf-8-sig")
    selected.to_csv(out_dir / "range_daily_selected.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out_dir / "performance_summary.csv", index=False, encoding="utf-8-sig")
    error_df.to_csv(out_dir / "errors.csv", index=False, encoding="utf-8-sig")
    _write_excel(out_dir / "closebet_range_backtest.xlsx", all_results, candidates, performance, selected, summary, error_df)

    counts = all_results["status"].value_counts()
    decisions = all_results.loc[all_results["status"].isin(CONFIRMED_STATUSES), "buy_day_decision"].value_counts()
    print()
    print(f"[DONE] {out_dir}")
    print(f"[STATUS] STRONG={int(counts.get('STRONG_CONFIRMED', 0))} CONFIRMED={int(counts.get('CONFIRMED', 0))} WATCH={int(counts.get('WATCH', 0))} REJECTED={int(counts.get('REJECTED', 0))}")
    print(f"[BUY DAY] BUY={int(decisions.get('BUY', 0))} WAIT_WEAK={int(decisions.get('WAIT_WEAK', 0))} WAIT_EXTENDED={int(decisions.get('WAIT_EXTENDED', 0))} SKIP_CANCEL={int(decisions.get('SKIP_CANCEL', 0))} SKIP_CHASE={int(decisions.get('SKIP_CHASE', 0))}")
    print(f"[EXECUTED] confirmed buy-day entries={len(performance)} daily_selected={len(selected)}")
    if not summary.empty:
        print()
        print(summary.head(24).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
