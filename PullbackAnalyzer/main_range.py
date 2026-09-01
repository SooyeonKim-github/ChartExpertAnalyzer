from __future__ import annotations

import argparse
from pathlib import Path
import re
import time
import numpy as np
import pandas as pd

from analyzer import PullbackAnalyzer
from config import DEFAULT_CONFIG, DEFAULT_INFO_EXCEL, RESULT_DIR
from data.pykrx_provider import PykrxDataProvider
from indicators import build_indicators
from universe import TickerUniverse

MILESTONES = (1, 5, 10, 20, 40, 60)
PROGRESS_EVERY_DATES = 100


def parse_date_range(text: str):
    parts = re.split(r"[~～]", str(text).replace(" ", ""))
    if len(parts) != 2:
        raise ValueError("YYYYMMDD~YYYYMMDD 형식으로 입력하세요.")
    start = pd.to_datetime(parts[0], format="%Y%m%d").normalize()
    end = pd.to_datetime(parts[1], format="%Y%m%d").normalize()
    if start > end:
        raise ValueError("시작일이 종료일보다 늦습니다.")
    return start, end


def _ticker(v) -> str:
    text = str(v or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text else ""


def load_membership(path: str, start, end):
    if not path:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Membership CSV 없음: {p}")
    m = pd.read_csv(p, encoding="utf-8-sig", dtype={"ticker": str})
    if not {"date", "ticker"}.issubset(m.columns):
        raise ValueError("membership CSV에는 date,ticker가 필요합니다.")
    m["date"] = pd.to_datetime(m["date"]).dt.normalize()
    m["ticker"] = m["ticker"].map(_ticker)
    return m[(m["date"] >= start) & (m["date"] <= end)].drop_duplicates(["date", "ticker"])


def _market_symbol(market: str) -> str:
    return "^KQ11" if "KOSDAQ" in str(market).upper() else "^KS11"


def forward_metrics(full: pd.DataFrame, pos: int, max_bars: int) -> dict:
    row = {}
    entry_pos = pos + 1
    if entry_pos >= len(full):
        return row
    entry = float(full["Open"].iloc[entry_pos])
    row["Entry_Date"] = full.index[entry_pos].strftime("%Y-%m-%d")
    row["Entry_Price_D1_Open"] = entry
    for n in MILESTONES:
        if n <= max_bars:
            j = pos + n
            row[f"D+{n}_Close_Return_Pct"] = ((float(full["Close"].iloc[j]) / entry - 1.0) * 100.0 if j < len(full) else np.nan)
    end = min(len(full)-1, pos + max_bars)
    future = full.iloc[entry_pos:end+1]
    row[f"Forward_Complete_{max_bars}D"] = int(pos + max_bars < len(full))
    row[f"MFE_{max_bars}D_Pct"] = (float(future["High"].max()) / entry - 1.0) * 100.0 if not future.empty else np.nan
    row[f"MAE_{max_bars}D_Pct"] = (float(future["Low"].min()) / entry - 1.0) * 100.0 if not future.empty else np.nan
    return row


def run_range(args) -> int:
    cfg = DEFAULT_CONFIG
    start, end = parse_date_range(args.date_range)
    membership = load_membership(args.membership_csv, start, end)
    universe = TickerUniverse(args.info_excel).get(args.top_n, args.sort_by)
    provider = PykrxDataProvider(use_cache=not args.no_cache)
    analyzer = PullbackAnalyzer(cfg)

    fetch_start = start - pd.Timedelta(days=cfg.history_calendar_days)
    fetch_end = min(end + pd.Timedelta(days=max(120, args.forward_bars*4)), pd.Timestamp.today().normalize())
    membership_by_ticker = {}
    if not membership.empty:
        membership_by_ticker = {t: g.set_index("date").sort_index() for t, g in membership.groupby("ticker")}
    market_cache = {}
    rows = []
    mode = "point-in-time liquidity membership" if not membership.empty else "static input universe"
    total_tickers = len(universe)
    range_started = time.perf_counter()
    print(f"[INFO] Pullback V1 range={start.date()}~{end.date()} universe={total_tickers} mode={mode}", flush=True)
    print(f"[INFO] data fetch range={fetch_start.date()}~{fetch_end.date()} forward_bars={args.forward_bars}", flush=True)

    for ti, info in enumerate(universe, 1):
        ticker_started = time.perf_counter()
        try:
            allowed = membership_by_ticker.get(info.ticker)
            if not membership.empty and allowed is None:
                print(f"[INFO] [{ti}/{total_tickers}] {info.ticker} {info.name} - skip: membership 없음", flush=True)
                continue
            allowed_dates = set(allowed.index) if allowed is not None else None

            print(
                f"[INFO] [{ti}/{total_tickers}] {info.ticker} {info.name} - OHLCV loading...",
                flush=True,
            )
            load_started = time.perf_counter()
            full = provider.get_ohlcv_by_date(
                info.ticker,
                fetch_start.strftime("%Y-%m-%d"),
                fetch_end.strftime("%Y-%m-%d"),
            )
            print(
                f"[INFO] [{ti}/{total_tickers}] {info.ticker} - OHLCV loaded "
                f"bars={len(full)} elapsed={time.perf_counter()-load_started:.1f}s",
                flush=True,
            )
            if len(full) < cfg.min_history_bars:
                print(
                    f"[INFO] [{ti}/{total_tickers}] {info.ticker} - skip: "
                    f"history {len(full)} < {cfg.min_history_bars}",
                    flush=True,
                )
                continue

            indicator_started = time.perf_counter()
            indicator_full = build_indicators(full, cfg)
            print(
                f"[INFO] [{ti}/{total_tickers}] {info.ticker} - indicators prepared once "
                f"elapsed={time.perf_counter()-indicator_started:.1f}s",
                flush=True,
            )

            symbol = _market_symbol(info.market)
            if symbol not in market_cache:
                try:
                    print(f"[INFO] market {symbol} - OHLCV loading...", flush=True)
                    market_started = time.perf_counter()
                    market_cache[symbol] = provider.get_ohlcv_by_date(
                        symbol,
                        fetch_start.strftime("%Y-%m-%d"),
                        fetch_end.strftime("%Y-%m-%d"),
                    )
                    market_rows = len(market_cache[symbol]) if market_cache[symbol] is not None else 0
                    print(
                        f"[INFO] market {symbol} - OHLCV loaded bars={market_rows} "
                        f"elapsed={time.perf_counter()-market_started:.1f}s",
                        flush=True,
                    )
                except Exception as exc:
                    print(f"[WARN] market {symbol}: {exc}", flush=True)
                    market_cache[symbol] = None
            market_full = market_cache.get(symbol)

            positions = [
                i for i, dt in enumerate(full.index)
                if start <= pd.Timestamp(dt).normalize() <= end
                and (allowed_dates is None or pd.Timestamp(dt).normalize() in allowed_dates)
                and i >= cfg.min_history_bars - 1
            ]
            if not positions:
                print(f"[INFO] [{ti}/{total_tickers}] {info.ticker} - 분석 가능한 거래일 없음", flush=True)
                continue

            ticker_row_start = len(rows)
            analyze_started = time.perf_counter()
            total_positions = len(positions)
            for pi, pos in enumerate(positions, 1):
                hist = full.iloc[:pos+1]
                indicator_hist = indicator_full.iloc[:pos+1]
                signal_date = hist.index[-1].strftime("%Y-%m-%d")
                market_hist = market_full.loc[market_full.index <= hist.index[-1]] if market_full is not None else None
                result = analyzer.analyze_precomputed(
                    info.ticker,
                    info.name,
                    info.market,
                    signal_date,
                    hist,
                    indicator_hist,
                    market_hist,
                )
                row = result.to_row()
                if allowed is not None:
                    key = pd.Timestamp(hist.index[-1]).normalize()
                    m = allowed.loc[key] if key in allowed.index else None
                    if isinstance(m, pd.DataFrame):
                        m = m.iloc[-1]
                    row["Universe_Rank"] = m.get("source_rank", np.nan) if m is not None else np.nan
                    row["Avg_Trading_Value_20D"] = m.get("avg_trading_value_20d", np.nan) if m is not None else np.nan
                    row["Universe_Mode"] = "LIQUIDITY_20D_POINT_IN_TIME"
                else:
                    row["Universe_Mode"] = "STATIC_INPUT_UNIVERSE"
                row.update(forward_metrics(full, pos, args.forward_bars))
                rows.append(row)

                if pi % PROGRESS_EVERY_DATES == 0 or pi == total_positions:
                    print(
                        f"[INFO] [{ti}/{total_tickers}] {info.ticker} - dates {pi}/{total_positions} "
                        f"ticker_rows={len(rows)-ticker_row_start} total_rows={len(rows)} "
                        f"elapsed={time.perf_counter()-analyze_started:.1f}s",
                        flush=True,
                    )

            print(
                f"[INFO] [{ti}/{total_tickers}] {info.ticker} {info.name} - done "
                f"rows={len(rows)-ticker_row_start} ticker_elapsed={time.perf_counter()-ticker_started:.1f}s "
                f"total_elapsed={time.perf_counter()-range_started:.1f}s",
                flush=True,
            )
        except Exception as exc:
            print(f"[WARN] [{ti}/{total_tickers}] {info.ticker} {info.name}: {exc}", flush=True)

    if not rows:
        print("[ERROR] 기간 분석 결과 없음", flush=True)
        return 1
    all_results = pd.DataFrame(rows)
    out_dir = RESULT_DIR / f"range_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = all_results[all_results["Status"].isin(["CONFIRMED", "WATCH"])].copy()
    confirmed = all_results[all_results["Status"].eq("CONFIRMED")].copy()
    all_results.to_csv(out_dir/"range_all_results.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(out_dir/"range_candidates.csv", index=False, encoding="utf-8-sig")
    confirmed.to_csv(out_dir/"events.csv", index=False, encoding="utf-8-sig")

    forward_cols = [c for c in all_results.columns if c.startswith("D+") and c.endswith("_Close_Return_Pct")]

    def summary_by(keys):
        base = all_results.groupby(keys, dropna=False).agg(
            Count=("Ticker", "count"),
            Avg_Score=("Score", "mean"),
            Avg_Timing=("Timing_Score", "mean"),
        ).reset_index()
        if forward_cols:
            ret = all_results.groupby(keys, dropna=False)[forward_cols].mean().reset_index()
            base = base.merge(ret, on=keys, how="left")
        return base

    by_status = summary_by(["Status"])
    by_type = summary_by(["Pullback_Type", "Pullback_Sequence"])
    by_status.to_csv(out_dir/"performance_by_status.csv", index=False, encoding="utf-8-sig")
    by_type.to_csv(out_dir/"performance_by_pullback_type.csv", index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(out_dir/"pullback_range_backtest.xlsx", engine="openpyxl") as writer:
        all_results.to_excel(writer, sheet_name="AllResults", index=False)
        candidates.to_excel(writer, sheet_name="Candidates", index=False)
        confirmed.to_excel(writer, sheet_name="Events", index=False)
        by_status.to_excel(writer, sheet_name="ByStatus", index=False)
        by_type.to_excel(writer, sheet_name="ByPullbackType", index=False)
        pd.DataFrame([{"Parameter": k, "Value": v} for k, v in cfg.to_dict().items()]).to_excel(
            writer, sheet_name="Config", index=False
        )
    print(f"[DONE] {out_dir}", flush=True)
    print(all_results["Status"].value_counts().to_string(), flush=True)
    print(f"[DONE] total_elapsed={time.perf_counter()-range_started:.1f}s rows={len(all_results)}", flush=True)
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="PullbackAnalyzer range backtest")
    p.add_argument("--date-range", required=True)
    p.add_argument("--info-excel", default=str(DEFAULT_INFO_EXCEL))
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--sort-by", default="trading_value", choices=["market_cap", "trading_value", "volume"])
    p.add_argument("--forward-bars", type=int, default=60)
    p.add_argument("--membership-csv", default="")
    p.add_argument("--no-cache", action="store_true")
    return p


if __name__ == "__main__":
    raise SystemExit(run_range(build_parser().parse_args()))
