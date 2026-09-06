from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from trend_following_analyzer import load_config, screen_date
from trend_following_analyzer.rule_catalog import rule_catalog_rows


def _write_subset(df, columns, path, encoding, *, sort_by=None, ascending=True):
    if df.empty:
        pd.DataFrame().to_csv(path, index=False, encoding=encoding)
        return
    out = df[columns].copy()
    if sort_by:
        out = out.sort_values(sort_by, ascending=ascending, na_position="last")
    out.to_csv(path, index=False, encoding=encoding)


def main():
    parser = argparse.ArgumentParser(
        description="Independent trend-following screener for Korean equities"
    )
    parser.add_argument("--date")
    parser.add_argument("--top-n", type=int, default=None)
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
    df = pd.DataFrame([row.to_dict() for row in results])
    out_dir = base_dir / args.out / resolved
    out_dir.mkdir(parents=True, exist_ok=True)
    encoding = cfg.get("output", {}).get("encoding", "utf-8-sig")

    paths = {
        "all": out_dir / "stage_market_screen.csv",
        "legacy": out_dir / "stage_screen.csv",
        "stage2": out_dir / "stage2_candidates.csv",
        "core": out_dir / "lecture_core_candidates.csv",
        "breadth": out_dir / "market_breadth_summary.csv",
        "intraday": out_dir / "market_intraday_summary.csv",
        "rs": out_dir / "relative_strength_summary.csv",
        "prior": out_dir / "prior_advance_summary.csv",
        "base": out_dir / "base_summary.csv",
        "rules": out_dir / "rule_catalog.csv",
    }

    df.to_csv(paths["all"], index=False, encoding=encoding)
    df.to_csv(paths["legacy"], index=False, encoding=encoding)
    pd.DataFrame(rule_catalog_rows()).to_csv(paths["rules"], index=False, encoding=encoding)

    if df.empty:
        for key in ("stage2", "core", "breadth", "intraday", "rs", "prior", "base"):
            pd.DataFrame().to_csv(paths[key], index=False, encoding=encoding)
    else:
        df[df["stage"].eq("STAGE_2")].to_csv(paths["stage2"], index=False, encoding=encoding)
        df[df["lecture_core_pass"].eq(True)].to_csv(paths["core"], index=False, encoding=encoding)

        breadth_cols = [
            "market", "market_breadth_status", "market_breadth_measurement",
            "market_breadth_source_mode", "market_breadth_membership_mode",
            "market_breadth_source_ticker_count", "market_breadth_failed_tickers",
            "market_breadth_universe_count", "market_breadth_eligible_count",
            "market_breadth_coverage_ratio", "market_new_high_52w_count",
            "market_new_low_52w_count", "market_new_high_52w_ratio",
            "market_new_low_52w_ratio", "market_new_high_low_spread",
            "market_breadth_5d_avg", "market_breadth_20d_avg",
            "market_breadth_5d_change", "market_breadth_20d_change",
            "market_breadth_direction", "market_breadth_snapshot_dates_loaded",
            "market_breadth_snapshot_dates_expected",
            "market_breadth_snapshot_date_coverage_ratio", "market_breadth_filter_applied",
        ]
        df[breadth_cols].drop_duplicates("market").sort_values("market").to_csv(
            paths["breadth"], index=False, encoding=encoding
        )

        intraday_cols = [
            col
            for col in df.columns
            if col == "market"
            or col.startswith("market_intraday_")
            or col.startswith("market_gap_")
            or col.startswith("market_open_close_")
            or col.startswith("market_close_location_")
            or col.startswith("market_recovery_")
            or col.startswith("market_fade_")
            or col.startswith("market_weak_open_")
            or col.startswith("market_strong_open_")
            or col.startswith("market_strong_close_")
            or col.startswith("market_weak_close_")
            or col.startswith("market_experimental_intraday_")
        ]
        df[intraday_cols].drop_duplicates("market").sort_values("market").to_csv(
            paths["intraday"], index=False, encoding=encoding
        )

        rs_cols = [
            "ticker", "name", "market", "trading_value_rank", "rs_status",
            "rs_measurement", "rs_percentile_scope", "stock_return_20d_pct",
            "benchmark_return_20d_pct", "rs_20d_pct", "stock_return_60d_pct",
            "benchmark_return_60d_pct", "rs_60d_pct", "rs_percentile_20d",
            "rs_percentile_60d", "rs_percentile_composite", "rs_label",
            "rs_experimental_20d_outperform_pass", "rs_experimental_60d_outperform_pass",
            "rs_experimental_percentile_pass", "rs_filter_applied",
        ]
        _write_subset(
            df, rs_cols, paths["rs"], encoding,
            sort_by=["rs_percentile_composite", "trading_value_rank"],
            ascending=[False, True],
        )

        prior_cols = [
            "ticker", "name", "market", "trading_value_rank", "stage",
            "lecture_core_pass", "prior_advance_status", "prior_advance_measurement",
            "prior_advance_anchor_mode", "prior_advance_anchor_is_base",
            "prior_advance_lookback_sessions", "prior_advance_recent_window_sessions",
            "prior_advance_low_date", "prior_advance_peak_date", "prior_advance_low",
            "prior_advance_peak", "prior_advance_pct", "prior_advance_duration_sessions",
            "prior_advance_sessions_from_peak_to_anchor", "prior_advance_peak_to_base_sessions",
            "prior_advance_current_vs_peak_pct", "prior_advance_peak_vs_ma150_pct",
            "prior_advance_drawdown_to_base_low_pct", "prior_advance_retention_ratio",
            "prior_advance_current_retention_ratio", "prior_return_60d_pct",
            "prior_return_120d_pct", "prior_advance_experimental_min_pass",
            "prior_advance_filter_applied",
        ]
        _write_subset(
            df, prior_cols, paths["prior"], encoding,
            sort_by=["prior_advance_pct", "trading_value_rank"],
            ascending=[False, True],
        )

        base_cols = [
            "ticker", "name", "market", "trading_value_rank", "stage",
            "lecture_core_pass", "base_status", "base_measurement", "base_start_date",
            "base_end_date", "base_duration_sessions", "base_high_date", "base_high",
            "base_low_date", "base_low", "base_depth_pct", "base_current_vs_high_pct",
            "base_atr_early_pct", "base_atr_late_pct", "base_atr_contraction_ratio",
            "base_range_early_pct", "base_range_late_pct", "base_range_contraction_ratio",
            "base_close_dispersion_pct", "base_experimental_quality_score",
            "base_experimental_depth_pass", "base_experimental_end_near_high_pass",
            "base_experimental_resistance_pass", "base_filter_applied",
            "prior_advance_anchor_mode", "prior_advance_pct",
            "prior_advance_peak_to_base_sessions", "prior_advance_drawdown_to_base_low_pct",
            "prior_advance_retention_ratio", "prior_advance_current_retention_ratio",
        ]
        _write_subset(
            df, base_cols, paths["base"], encoding,
            sort_by=["base_experimental_quality_score", "trading_value_rank"],
            ascending=[False, True],
        )

    print("\n============================================")
    print(f" TrendFollowingAnalyzer | {resolved}")
    print(" Phase 1-7: Stage / Market / Breadth / Intraday / RS / Prior Advance / Base")
    print("============================================")
    print(" Active filters : LECTURE_CORE MA150 rules only")
    print(" 52W Breadth    : BACKTEST_ONLY")
    print(" Intraday Proxy : BACKTEST_ONLY")
    print(" Relative Str.  : BACKTEST_ONLY")
    print(" Prior Advance  : BACKTEST_ONLY; re-anchored to detected Base when available")
    print(" Generic Base   : BACKTEST_ONLY; price structure only (volume contraction is Phase 8)")

    if not df.empty:
        print("\n[MARKET COUNTS]")
        print(df["market"].value_counts(dropna=False).to_string())
        print("\n[52W BREADTH SOURCE]")
        print(
            df[[
                "market", "market_breadth_source_mode", "market_breadth_membership_mode",
                "market_breadth_source_ticker_count", "market_breadth_direction",
            ]].drop_duplicates("market").sort_values("market").to_string(index=False)
        )
        print("\n[INTRADAY STRENGTH]")
        print(
            df[[
                "market", "market_intraday_status", "market_intraday_label",
                "market_close_location_value", "market_intraday_direction",
            ]].drop_duplicates("market").sort_values("market").to_string(index=False)
        )
        print("\n[BASE STATUS - BACKTEST ONLY]")
        print(df["base_status"].value_counts(dropna=False).to_string())
        print("\n[BASE + PRIOR ADVANCE LINK]")
        print(
            df[[
                "ticker", "name", "market", "stage", "base_status", "base_duration_sessions",
                "base_depth_pct", "base_current_vs_high_pct", "base_atr_contraction_ratio",
                "base_range_contraction_ratio", "base_experimental_quality_score",
                "prior_advance_pct", "prior_advance_peak_to_base_sessions",
                "prior_advance_retention_ratio", "prior_advance_current_retention_ratio",
            ]]
            .sort_values(
                ["base_experimental_quality_score", "prior_advance_retention_ratio"],
                ascending=[False, False],
                na_position="last",
            )
            .head(30)
            .to_string(index=False)
        )
        print("\n[STAGE COUNTS]")
        print(df["stage"].value_counts(dropna=False).to_string())

    for path in paths.values():
        print(f"[DONE] {path}")


if __name__ == "__main__":
    main()
