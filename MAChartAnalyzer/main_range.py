from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd

from analyzer import MAChartSignalAnalyzer
from config import DEFAULT_CONFIG, DEFAULT_INFO_EXCEL, RESULT_DIR
from data_provider import PykrxDataProvider
from universe import TickerUniverse


MILESTONES = (1, 5, 10, 20, 40, 60)


def parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    parts = re.split(r"[~～]", str(text).replace(" ", ""))
    if len(parts) != 2:
        raise ValueError("YYYYMMDD~YYYYMMDD 형식으로 입력하세요.")
    start = pd.to_datetime(parts[0], format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(parts[1], format="%Y%m%d", errors="raise").normalize()
    if start > end:
        raise ValueError("시작일이 종료일보다 늦습니다.")
    return start, end


def forward_metrics(full: pd.DataFrame, pos: int, max_bars: int) -> dict:
    base = float(full["Close"].iloc[pos])
    row: dict = {}
    for n in MILESTONES:
        if n > max_bars:
            continue
        j = pos + n
        row[f"D+{n}_Close_Return_Pct"] = (
            (float(full["Close"].iloc[j]) / base - 1.0) * 100.0 if j < len(full) else np.nan
        )

    end = min(len(full) - 1, pos + max_bars)
    future = full.iloc[pos + 1 : end + 1]
    row[f"Forward_Complete_{max_bars}D"] = int(pos + max_bars < len(full))
    if future.empty:
        row[f"MFE_{max_bars}D_Pct"] = np.nan
        row[f"MAE_{max_bars}D_Pct"] = np.nan
    else:
        row[f"MFE_{max_bars}D_Pct"] = (float(future["High"].max()) / base - 1.0) * 100.0
        row[f"MAE_{max_bars}D_Pct"] = (float(future["Low"].min()) / base - 1.0) * 100.0
    return row


def run_range(args) -> int:
    cfg = DEFAULT_CONFIG
    start, end = parse_date_range(args.date_range)
    universe = TickerUniverse(args.info_excel).get(args.top_n, args.sort_by)
    provider = PykrxDataProvider(use_cache=not args.no_cache)
    analyzer = MAChartSignalAnalyzer(cfg)

    fetch_start = start - pd.Timedelta(days=cfg.history_calendar_days)
    requested_future_end = end + pd.Timedelta(days=max(120, args.forward_bars * 4))
    fetch_end = min(requested_future_end, pd.Timestamp.today().normalize())

    print(
        f"[INFO] MA range={start.date()}~{end.date()} universe={len(universe)} "
        f"fetch={fetch_start.date()}~{fetch_end.date()} forward={args.forward_bars}"
    )

    rows: list[dict] = []
    for ti, info in enumerate(universe, 1):
        try:
            full = provider.get_ohlcv(
                info.ticker,
                fetch_start.strftime("%Y-%m-%d"),
                fetch_end.strftime("%Y-%m-%d"),
            )
            if len(full) < cfg.min_history_bars:
                continue

            positions = [
                i
                for i, dt in enumerate(full.index)
                if start <= pd.Timestamp(dt).normalize() <= end
            ]
            for pos in positions:
                if pos < cfg.min_history_bars - 1:
                    continue
                hist = full.iloc[: pos + 1]
                signal_date = hist.index[-1].strftime("%Y-%m-%d")
                result = analyzer.analyze(
                    info.ticker,
                    info.name,
                    info.market,
                    signal_date,
                    hist,
                )
                row = result.to_row()
                row.update(forward_metrics(full, pos, args.forward_bars))
                rows.append(row)

            if ti % 10 == 0:
                print(f"[INFO] progress {ti}/{len(universe)} rows={len(rows)}")
        except Exception as exc:
            print(f"[WARN] {info.ticker} {info.name}: {exc}")

    if not rows:
        print("[ERROR] 기간 분석 결과 없음")
        return 1

    all_results = pd.DataFrame(rows)
    range_key = f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
    out_dir = RESULT_DIR / f"range_{range_key}"
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = all_results[all_results["Status"].isin(["CONFIRMED", "WATCH"])].copy()
    all_results.to_csv(out_dir / "range_all_results.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(out_dir / "range_candidates.csv", index=False, encoding="utf-8-sig")

    summary = (
        all_results.groupby("Status", dropna=False)
        .agg(Count=("Ticker", "count"), Avg_Score=("Score", "mean"))
        .reset_index()
    )
    forward_cols = [c for c in all_results.columns if c.startswith("D+") and c.endswith("_Close_Return_Pct")]
    if forward_cols:
        avg = all_results.groupby("Status")[forward_cols].mean().reset_index()
        summary = summary.merge(avg, on="Status", how="left")

    with pd.ExcelWriter(out_dir / "ma_range_backtest.xlsx", engine="openpyxl") as writer:
        all_results.to_excel(writer, sheet_name="AllResults", index=False)
        candidates.to_excel(writer, sheet_name="Candidates", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
        cfg_rows = [{"Parameter": k, "Value": v} for k, v in cfg.to_dict().items()]
        cfg_rows += [
            {"Parameter": "date_range", "Value": args.date_range},
            {"Parameter": "top_n", "Value": args.top_n},
            {"Parameter": "sort_by", "Value": args.sort_by},
            {"Parameter": "forward_bars", "Value": args.forward_bars},
        ]
        pd.DataFrame(cfg_rows).to_excel(writer, sheet_name="Config", index=False)

    counts = all_results["Status"].value_counts()
    print(f"[DONE] {out_dir}")
    print(
        f"[INFO] CONFIRMED={int(counts.get('CONFIRMED', 0))} "
        f"WATCH={int(counts.get('WATCH', 0))} "
        f"REJECTED={int(counts.get('REJECTED', 0))}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="MAChartAnalyzer range backtest")
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--info-excel", default=str(DEFAULT_INFO_EXCEL))
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument(
        "--sort-by",
        default="market_cap",
        choices=["market_cap", "trading_value", "volume"],
    )
    p.add_argument("--forward-bars", type=int, default=60)
    p.add_argument("--no-cache", action="store_true")
    return p


if __name__ == "__main__":
    raise SystemExit(run_range(build_parser().parse_args()))
