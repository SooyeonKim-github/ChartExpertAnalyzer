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
    breadth_path = out_dir / "market_breadth_summary.csv"
    rule_path = out_dir / "rule_catalog.csv"

    df.to_csv(all_path, index=False, encoding=encoding)
    df.to_csv(legacy_path, index=False, encoding=encoding)
    pd.DataFrame(rule_catalog_rows()).to_csv(rule_path, index=False, encoding=encoding)

    if df.empty:
        df.to_csv(stage2_path, index=False, encoding=encoding)
        df.to_csv(core_path, index=False, encoding=encoding)
        pd.DataFrame().to_csv(breadth_path, index=False, encoding=encoding)
    else:
        df[df["stage"].eq("STAGE_2")].to_csv(stage2_path, index=False, encoding=encoding)
        df[df["lecture_core_pass"].eq(True)].to_csv(core_path, index=False, encoding=encoding)

        breadth_cols = [
            "market",
            "market_breadth_status",
            "market_breadth_measurement",
            "market_breadth_universe_count",
            "market_breadth_eligible_count",
            "market_breadth_coverage_ratio",
            "market_new_high_52w_count",
            "market_new_low_52w_count",
            "market_new_high_52w_ratio",
            "market_new_low_52w_ratio",
            "market_new_high_low_spread",
            "market_breadth_5d_avg",
            "market_breadth_20d_avg",
            "market_breadth_5d_change",
            "market_breadth_20d_change",
            "market_breadth_direction",
            "market_breadth_snapshot_dates_loaded",
            "market_breadth_snapshot_dates_expected",
            "market_breadth_snapshot_date_coverage_ratio",
            "market_breadth_filter_applied",
        ]
        df[breadth_cols].drop_duplicates("market").sort_values("market").to_csv(
            breadth_path, index=False, encoding=encoding
        )

    print("\n============================================")
    print(f" TrendFollowingAnalyzer | {resolved}")
    print(" Phase 1-4B: Stage / Market Regime / 52W Breadth")
    print("============================================")
    print(" Active filters : LECTURE_CORE MA150 rules only")
    print(" 52W Breadth    : BACKTEST_ONLY (close-high proxy, not gating)")
    print(" Experimental   : recorded only, not gating")

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

        breadth_cols = [
            "market",
            "market_breadth_status",
            "market_breadth_coverage_ratio",
            "market_new_high_52w_ratio",
            "market_new_low_52w_ratio",
            "market_new_high_low_spread",
            "market_breadth_5d_change",
            "market_breadth_20d_change",
            "market_breadth_direction",
        ]
        breadth_view = df[breadth_cols].drop_duplicates("market").sort_values("market")
        print("\n[52W BREADTH - BACKTEST ONLY]")
        print(breadth_view.to_string(index=False))

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
    print(f"[DONE] {breadth_path}")
    print(f"[DONE] {rule_path}")


if __name__ == "__main__":
    main()
