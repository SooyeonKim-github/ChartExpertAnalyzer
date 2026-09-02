from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from leader_stock_analyzer import load_config, screen_date


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent Korean market leader-stock screener")
    parser.add_argument("--date", help="Scan date YYYYMMDD. Defaults to latest available market date.")
    parser.add_argument("--top-n", type=int, default=None, help="Top N by same-day trading value")
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    cfg = load_config(base_dir / args.config)
    resolved, results = screen_date(cfg, scan_date=args.date, top_n=args.top_n, base_dir=base_dir)
    rows = [r.to_dict() for r in results]
    df = pd.DataFrame(rows)
    out_dir = base_dir / args.out / resolved
    out_dir.mkdir(parents=True, exist_ok=True)
    all_path = out_dir / "leader_screen.csv"
    cand_path = out_dir / "confirmed_candidates.csv"
    df.to_csv(all_path, index=False, encoding="utf-8-sig")
    if not df.empty:
        df[df["status"].isin(["STRONG_CONFIRMED", "CONFIRMED"])].to_csv(cand_path, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(cand_path, index=False, encoding="utf-8-sig")

    print("\n============================================")
    print(f" LeaderStockAnalyzer | {resolved}")
    print("============================================")
    if df.empty:
        print("No analyzable symbols.")
    else:
        cols = ["market_leader_rank", "ticker", "name", "status", "leader_score", "timing_score", "chase_risk", "return_pct", "trading_value_rank", "entry_state"]
        print(df[cols].head(20).to_string(index=False))
    print(f"\n[DONE] {all_path}")
    print(f"[DONE] {cand_path}")


if __name__ == "__main__":
    main()
