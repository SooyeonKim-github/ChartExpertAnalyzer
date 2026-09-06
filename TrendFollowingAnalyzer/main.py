from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from trend_following_analyzer import load_config, screen_date
from trend_following_analyzer.rule_catalog import rule_catalog_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independent trend-following screener for Korean equities"
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
    all_path = out_dir / "stage_market_screen.csv"
    legacy_path = out_dir / "stage_screen.csv"
    stage2_path = out_dir / "stage2_candidates.csv"
    core_path = out_dir / "lecture_core_candidates.csv"
    rule_path = out_dir / "rule_catalog.csv"

    df.to_csv(all_path, index=False, encoding=encoding)
    df.to_csv(legacy_path, index=False, encoding=encoding)
    pd.DataFrame(rule_catalog_rows()).to_csv(rule_path, index=False, encoding=encoding)

    if df.empty:
        df.to_csv(stage2_path, index=False, encoding=encoding)
        df.to_csv(core_path, index=False, encoding=encoding)
    else:
        df[df["stage"].eq("STAGE_2")].to_csv(stage2_path, index=False, encoding=encoding)
        df[df["lecture_core_pass"].eq(True)].to_csv(core_path, index=False, encoding=encoding)

    print("\n============================================")
    print(f" TrendFollowingAnalyzer | {resolved}")
    print(" Phase 1-4A: MA50 / MA150 / Stage / Market Regime")
    print("============================================")
    print(" Active filters : LECTURE_CORE only")
    print(" Experimental   : recorded only, not gating")
    print(" 52W Breadth    : planned for Phase 4B")

    if df.empty:
        print("No analyzable symbols.")
    else:
        market_cols = [
            "market",
            "market_regime",
            "market_eligible",
            "market_index_close",
            "market_index_ma150",
            "market_index_ma150_slope_pct",
            "market_regime_reason",
        ]
        market_view = df[market_cols].drop_duplicates("market").sort_values("market")
        print("\n[MARKET REGIME]")
        print(market_view.to_string(index=False))

        cols = [
            "ticker",
            "name",
            "market",
            "market_regime",
            "stage",
            "lecture_core_pass",
            "close",
            "ma150",
            "ma150_slope_pct",
            "stage_experimental_slope_pass",
            "market_experimental_slope_threshold_pass",
            "market_experimental_ma50_alignment_pass",
        ]
        cols = [c for c in cols if c in df.columns]
        print("\n[TOP SCREEN]")
        print(df[cols].head(30).to_string(index=False))
        print("\n[STAGE COUNTS]")
        print(df["stage"].value_counts(dropna=False).to_string())

    print(f"\n[DONE] {all_path}")
    print(f"[DONE] {stage2_path}")
    print(f"[DONE] {core_path}")
    print(f"[DONE] {rule_path}")


if __name__ == "__main__":
    main()
