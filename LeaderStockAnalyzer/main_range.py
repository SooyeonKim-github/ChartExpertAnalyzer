from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from leader_stock_analyzer import load_config, screen_date
from leader_stock_analyzer.data_provider import PyKrxLeaderDataProvider


def _parse_range(value: str) -> tuple[str, str]:
    if "~" not in value:
        raise argparse.ArgumentTypeError("Use YYYYMMDD~YYYYMMDD")
    start, end = value.split("~", 1)
    pd.Timestamp(start); pd.Timestamp(end)
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


def _forward_returns(provider: PyKrxLeaderDataProvider, ticker: str, scan_date: str, horizons: list[int]) -> dict[str, float | None]:
    future_calendar_days = max(horizons) * 2 + 30
    df = provider.get_daily(ticker, scan_date, future_days=future_calendar_days)
    df = df[df.index >= pd.Timestamp(scan_date)].copy()
    if df.empty:
        return {f"D+{h}": None for h in horizons}
    entry = float(df.iloc[0]["close"])
    out: dict[str, float | None] = {}
    for h in horizons:
        if len(df) <= h or entry <= 0:
            out[f"D+{h}"] = None
        else:
            out[f"D+{h}"] = round((float(df.iloc[h]["close"]) / entry - 1.0) * 100.0, 3)
    return out


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
    dates = _trading_dates(start, end)
    rows: list[dict] = []
    horizons = [1, 5, 20, 60]
    for i, d in enumerate(dates, start=1):
        print(f"\n[{i}/{len(dates)}] {d}")
        _, results = screen_date(cfg, scan_date=d, top_n=args.top_n, base_dir=base_dir, progress=False)
        for r in results:
            rec = r.to_dict()
            rec.update(_forward_returns(provider, r.ticker, d, horizons))
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
    print(f"\n[DONE] {all_path}")
    print(f"[DONE] {cand_path}")


if __name__ == "__main__":
    main()
