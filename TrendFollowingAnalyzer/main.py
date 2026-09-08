from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from trend_following_analyzer import load_config, screen_date
from trend_following_analyzer.rule_catalog import rule_catalog_rows
from trend_following_analyzer.structure.enrichment import enrich_structure_features


def _write_subset(df, columns, path, encoding, *, sort_by=None, ascending=True):
    if df.empty:
        pd.DataFrame().to_csv(path, index=False, encoding=encoding)
        return
    cols = [c for c in columns if c in df.columns]
    out = df[cols].copy()
    if sort_by:
        usable_sort = [c for c in sort_by if c in out.columns]
        if usable_sort:
            if isinstance(ascending, list):
                asc = [ascending[sort_by.index(c)] for c in usable_sort]
            else:
                asc = ascending
            out = out.sort_values(usable_sort, ascending=asc, na_position="last")
    out.to_csv(path, index=False, encoding=encoding)


def main():
    parser = argparse.ArgumentParser(description="Independent trend-following screener for Korean equities")
    parser.add_argument("--date")
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--universe-xlsx", default=None)
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    cfg = load_config(base_dir / args.config)
    resolved, results = screen_date(cfg, scan_date=args.date, top_n=args.top_n, base_dir=base_dir, universe_xlsx=args.universe_xlsx)
    df = pd.DataFrame([r.to_dict() for r in results])
    if not df.empty:
        df = enrich_structure_features(df, cfg, resolved=resolved, base_dir=base_dir, universe_xlsx=args.universe_xlsx)

    out_dir = base_dir / args.out / resolved
    out_dir.mkdir(parents=True, exist_ok=True)
    encoding = cfg.get("output", {}).get("encoding", "utf-8-sig")
    paths = {
        "all": out_dir / "stage_market_screen.csv", "legacy": out_dir / "stage_screen.csv",
        "stage2": out_dir / "stage2_candidates.csv", "core": out_dir / "lecture_core_candidates.csv",
        "breadth": out_dir / "market_breadth_summary.csv", "intraday": out_dir / "market_intraday_summary.csv",
        "rs": out_dir / "relative_strength_summary.csv", "prior": out_dir / "prior_advance_summary.csv",
        "base": out_dir / "base_summary.csv", "volume": out_dir / "volume_contraction_summary.csv",
        "breakout": out_dir / "breakout_summary.csv", "rules": out_dir / "rule_catalog.csv",
    }
    df.to_csv(paths["all"], index=False, encoding=encoding)
    df.to_csv(paths["legacy"], index=False, encoding=encoding)
    pd.DataFrame(rule_catalog_rows()).to_csv(paths["rules"], index=False, encoding=encoding)

    if df.empty:
        for key in ("stage2", "core", "breadth", "intraday", "rs", "prior", "base", "volume", "breakout"):
            pd.DataFrame().to_csv(paths[key], index=False, encoding=encoding)
    else:
        df[df["stage"].eq("STAGE_2")].to_csv(paths["stage2"], index=False, encoding=encoding)
        df[df["lecture_core_pass"].eq(True)].to_csv(paths["core"], index=False, encoding=encoding)
        breadth_cols = ["market", "market_breadth_status", "market_breadth_measurement", "market_breadth_source_mode", "market_breadth_membership_mode", "market_breadth_source_ticker_count", "market_breadth_failed_tickers", "market_breadth_universe_count", "market_breadth_eligible_count", "market_breadth_coverage_ratio", "market_new_high_52w_count", "market_new_low_52w_count", "market_new_high_52w_ratio", "market_new_low_52w_ratio", "market_new_high_low_spread", "market_breadth_5d_avg", "market_breadth_20d_avg", "market_breadth_5d_change", "market_breadth_20d_change", "market_breadth_direction", "market_breadth_snapshot_dates_loaded", "market_breadth_snapshot_dates_expected", "market_breadth_snapshot_date_coverage_ratio", "market_breadth_filter_applied"]
        df[breadth_cols].drop_duplicates("market").sort_values("market").to_csv(paths["breadth"], index=False, encoding=encoding)
        intraday_cols = [c for c in df.columns if c == "market" or c.startswith("market_intraday_") or c.startswith("market_gap_") or c.startswith("market_open_close_") or c.startswith("market_close_location_") or c.startswith("market_recovery_") or c.startswith("market_fade_") or c.startswith("market_weak_open_") or c.startswith("market_strong_open_") or c.startswith("market_strong_close_") or c.startswith("market_weak_close_") or c.startswith("market_experimental_intraday_")]
        df[intraday_cols].drop_duplicates("market").sort_values("market").to_csv(paths["intraday"], index=False, encoding=encoding)
        rs_cols = ["ticker", "name", "market", "trading_value_rank", "rs_status", "rs_measurement", "rs_percentile_scope", "stock_return_20d_pct", "benchmark_return_20d_pct", "rs_20d_pct", "stock_return_60d_pct", "benchmark_return_60d_pct", "rs_60d_pct", "rs_percentile_20d", "rs_percentile_60d", "rs_percentile_composite", "rs_label", "rs_experimental_20d_outperform_pass", "rs_experimental_60d_outperform_pass", "rs_experimental_percentile_pass", "rs_filter_applied"]
        _write_subset(df, rs_cols, paths["rs"], encoding, sort_by=["rs_percentile_composite", "trading_value_rank"], ascending=[False, True])
        prior_cols = [c for c in df.columns if c in {"ticker", "name", "market", "trading_value_rank", "stage", "lecture_core_pass"} or c.startswith("prior_advance_")]
        _write_subset(df, prior_cols, paths["prior"], encoding, sort_by=["prior_advance_pct", "trading_value_rank"], ascending=[False, True])
        base_cols = [c for c in df.columns if c in {"ticker", "name", "market", "trading_value_rank", "stage", "lecture_core_pass"} or c.startswith("base_") or c in {"prior_advance_anchor_mode", "prior_advance_pct", "prior_advance_peak_to_base_sessions", "prior_advance_drawdown_to_base_low_pct", "prior_advance_retention_ratio", "prior_advance_current_retention_ratio"}]
        _write_subset(df, base_cols, paths["base"], encoding, sort_by=["base_experimental_quality_score", "trading_value_rank"], ascending=[False, True])
        volume_cols = [c for c in df.columns if c in {"ticker", "name", "market", "trading_value_rank", "stage", "lecture_core_pass", "base_status", "base_start_date"} or c.startswith("volume_") or c.startswith("experimental_stack_core_base_volume") or c.startswith("experimental_stack_core_base_prior_volume")]
        _write_subset(df, volume_cols, paths["volume"], encoding, sort_by=["volume_experimental_quality_score", "trading_value_rank"], ascending=[False, True])
        breakout_cols = [c for c in df.columns if c in {"ticker", "name", "market", "trading_value_rank", "stage", "lecture_core_pass"} or c.startswith("breakout_") or c == "experimental_stack_core_full_breakout_pass"]
        _write_subset(df, breakout_cols, paths["breakout"], encoding, sort_by=["breakout_experimental_signal_pass", "breakout_volume_ratio", "trading_value_rank"], ascending=[False, False, True])

    print("\n============================================")
    print(f" TrendFollowingAnalyzer | {resolved}")
    print(" Phase 1-9: Stage / Market / RS / Prior / Base / Volume / Breakout")
    print("============================================")
    print(" Active filters : LECTURE_CORE MA150 rules only")
    print(" Generic Base   : BACKTEST_ONLY")
    print(" Volume Dry-up  : BACKTEST_ONLY")
    print(" Breakout       : BACKTEST_ONLY")
    print(" Range V1       : run_range_backtest.bat")
    if not df.empty:
        print("\n[MARKET COUNTS]")
        print(df["market"].value_counts(dropna=False).to_string())
        print("\n[BASE STATUS - BACKTEST ONLY]")
        print(df["base_status"].value_counts(dropna=False).to_string())
        if "volume_contraction_status" in df.columns:
            print("\n[VOLUME CONTRACTION - BACKTEST ONLY]")
            cols = [c for c in ["ticker", "name", "market", "base_status", "volume_contraction_ratio", "volume_median_contraction_ratio", "volume_down_vs_up_volume_ratio", "volume_dry_up_day_ratio", "volume_experimental_contraction_pass"] if c in df.columns]
            print(df[cols].sort_values("volume_contraction_ratio", na_position="last").head(30).to_string(index=False))
        if "breakout_status" in df.columns:
            print("\n[BREAKOUT - BACKTEST ONLY]")
            print(df["breakout_status"].value_counts(dropna=False).to_string())
            cols = [c for c in ["ticker", "name", "market", "breakout_status", "breakout_level", "breakout_close_breakout_pct", "breakout_volume_ratio", "breakout_experimental_signal_pass", "experimental_stack_core_full_breakout_pass"] if c in df.columns]
            print(df[cols].sort_values(["breakout_experimental_signal_pass", "breakout_volume_ratio"], ascending=[False, False], na_position="last").head(30).to_string(index=False))
        print("\n[STAGE COUNTS]")
        print(df["stage"].value_counts(dropna=False).to_string())
    for path in paths.values():
        print(f"[DONE] {path}")


if __name__ == "__main__":
    main()
