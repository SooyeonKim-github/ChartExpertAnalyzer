from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from leader_stock_analyzer import load_config, screen_date
from leader_stock_analyzer.data_provider import PyKrxLeaderDataProvider
from leader_stock_analyzer.performance import ForwardPerformanceEngine, PerformanceAttributionEngine


def _parse_range(value: str) -> tuple[str, str]:
    if "~" not in value:
        raise argparse.ArgumentTypeError("Use YYYYMMDD~YYYYMMDD")
    start, end = value.split("~", 1)
    pd.Timestamp(start)
    pd.Timestamp(end)
    return start, end


def _trading_dates(start: str, end: str) -> list[str]:
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx is not installed") from exc
    df = stock.get_index_ohlcv_by_date(start, end, "1001")
    if df is None or df.empty:
        raise RuntimeError("Could not load KOSPI trading dates")
    return [pd.Timestamp(x).strftime("%Y%m%d") for x in df.index]


def main() -> None:
    p = argparse.ArgumentParser(description="LeaderStockAnalyzer point-in-time range scan")
    p.add_argument("--date-range", required=True, type=_parse_range)
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--out", default="results")
    args = p.parse_args()
    start, end = args.date_range

    base_dir = Path(__file__).resolve().parent
    cfg = load_config(base_dir / args.config)
    provider = PyKrxLeaderDataProvider(cfg, base_dir)
    performance = ForwardPerformanceEngine(cfg)
    attribution = PerformanceAttributionEngine(cfg)
    dates = _trading_dates(start, end)
    rows: list[dict] = []

    max_horizon = max(performance.horizons + performance.excursion_horizons)
    future_calendar_days = max_horizon * 2 + 30
    range_calendar_days = max(0, (pd.Timestamp(end) - pd.Timestamp(start)).days)
    full_series_future_days = range_calendar_days + future_calendar_days
    forward_cache: dict[str, pd.DataFrame] = {}

    for i, d in enumerate(dates, start=1):
        print(f"\n[{i}/{len(dates)}] {d}")
        _, results = screen_date(cfg, scan_date=d, top_n=args.top_n, base_dir=base_dir, progress=False)
        for r in results:
            rec = r.to_dict()
            ticker = str(r.ticker).zfill(6)
            try:
                if ticker not in forward_cache:
                    forward_cache[ticker] = provider.get_daily(
                        ticker,
                        start,
                        future_days=full_series_future_days,
                    )
                rec.update(
                    performance.evaluate(
                        forward_cache[ticker],
                        d,
                        breakout_reference=r.breakout_reference,
                    )
                )
            except Exception as exc:
                print(f"[WARN] forward performance {d} {ticker} {r.name}: {exc}")
                rec.update(performance.evaluate(pd.DataFrame(), d, breakout_reference=r.breakout_reference))
            rows.append(rec)

    df = pd.DataFrame(rows)
    out_dir = base_dir / args.out / f"range_{start}_{end}"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_path = out_dir / "range_all_results.csv"
    cand_path = out_dir / "range_candidates.csv"
    df.to_csv(all_path, index=False, encoding="utf-8-sig")
    if not df.empty:
        df[df["status"].isin(["STRONG_CONFIRMED", "CONFIRMED"])].to_csv(cand_path, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(cand_path, index=False, encoding="utf-8-sig")

    perf_dir = out_dir / "performance"
    report_paths = attribution.write_reports(df, perf_dir)

    print(f"\n[DONE] {all_path}")
    print(f"[DONE] {cand_path}")
    print(f"[DONE] performance reports -> {perf_dir}")
    for name, path in report_paths.items():
        print(f"       {name}: {path.name}")


if __name__ == "__main__":
    main()
