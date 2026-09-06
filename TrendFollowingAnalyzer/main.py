from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from trend_following_analyzer import load_config, screen_date


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independent trend-following stage screener for Korean equities"
    )
    parser.add_argument("--date", help="Scan date YYYYMMDD. Defaults to latest trading date.")
    parser.add_argument("--top-n", type=int, default=None, help="Top N by scan-date trading value")
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--universe-xlsx", default=None)
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    cfg = load_config(base_dir / args.config)
    resolved, results = screen_date(
        cfg,
        scan_date=args.date,
        top_n=args.top_n,
        base_dir=base_dir,
        universe_xlsx=args.universe_xlsx,
    )

    df = pd.DataFrame([r.to_dict() for r in results])
    out_dir = base_dir / args.out / resolved
    out_dir.mkdir(parents=True, exist_ok=True)

    encoding = cfg.get("output", {}).get("encoding", "utf-8-sig")
    all_path = out_dir / "stage_screen.csv"
    stage2_path = out_dir / "stage2_candidates.csv"

    df.to_csv(all_path, index=False, encoding=encoding)
    if df.empty:
        df.to_csv(stage2_path, index=False, encoding=encoding)
    else:
        df[df["stage"].eq("STAGE_2")].to_csv(stage2_path, index=False, encoding=encoding)

    print("\n============================================")
    print(f" TrendFollowingAnalyzer | {resolved}")
    print(" Phase 1-3: MA50 / MA150 / Stage Detector")
    print("============================================")

    if df.empty:
        print("No analyzable symbols.")
    else:
        cols = [
            "ticker",
            "name",
            "market",
            "stage",
            "trend_eligible",
            "close",
            "ma50",
            "ma150",
            "ma150_slope_pct",
            "close_vs_ma150_pct",
            "stage_reason",
        ]
        cols = [c for c in cols if c in df.columns]
        print(df[cols].head(30).to_string(index=False))
        print("\n[STAGE COUNTS]")
        print(df["stage"].value_counts(dropna=False).to_string())

    print(f"\n[DONE] {all_path}")
    print(f"[DONE] {stage2_path}")


if __name__ == "__main__":
    main()
