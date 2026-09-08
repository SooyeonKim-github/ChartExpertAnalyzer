from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from trend_following_analyzer import load_config
from trend_following_analyzer.backtest import run_range_v1


def _resolve_universe_xlsx(base_dir: Path, explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_path = os.environ.get("LIQUIDITY_UNIVERSE_XLSX", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    repo_root = base_dir.parent
    candidates.extend([
        base_dir / "KOSPI_Info.xlsx",
        repo_root / "KJBChartAnalyzer" / "KOSPI_Info.xlsx",
    ])
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Universe Excel not found. Use --universe-xlsx or LIQUIDITY_UNIVERSE_XLSX.\n"
        + "\n".join(f"- {p}" for p in candidates)
    )


def _safe_range_key(date_range: str) -> str:
    return str(date_range).strip().replace(" ", "").replace("~", "_").replace("～", "_")


def main() -> None:
    parser = argparse.ArgumentParser(description="TrendFollowingAnalyzer V1 point-in-time range backtest")
    parser.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--universe-xlsx", default=None)
    parser.add_argument("--out", default="results_range")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    cfg = load_config(base_dir / args.config)
    top_n = int(args.top_n or cfg.get("universe", {}).get("top_n", 100))
    universe_xlsx = _resolve_universe_xlsx(base_dir, args.universe_xlsx)

    results, summary, errors, meta = run_range_v1(
        cfg,
        date_range=args.date_range,
        top_n=top_n,
        base_dir=base_dir,
        universe_xlsx=universe_xlsx,
    )

    out_dir = base_dir / args.out / _safe_range_key(args.date_range)
    out_dir.mkdir(parents=True, exist_ok=True)
    encoding = cfg.get("output", {}).get("encoding", "utf-8-sig")

    all_path = out_dir / "range_all_results.csv"
    core_path = out_dir / "range_core_results.csv"
    candidates_path = out_dir / "range_candidates.csv"
    summary_path = out_dir / "range_strategy_summary.csv"
    errors_path = out_dir / "range_errors.csv"
    meta_csv_path = out_dir / "range_meta.csv"
    meta_json_path = out_dir / "range_meta.json"

    results.to_csv(all_path, index=False, encoding=encoding)
    if results.empty:
        pd.DataFrame().to_csv(core_path, index=False, encoding=encoding)
        pd.DataFrame().to_csv(candidates_path, index=False, encoding=encoding)
    else:
        results[results.get("strategy_core", False).fillna(False).astype(bool)].to_csv(
            core_path, index=False, encoding=encoding
        )
        experiment_cols = [
            "strategy_core_base",
            "strategy_core_base_prior",
            "strategy_core_base_volume",
            "strategy_core_base_prior_volume",
            "strategy_core_breakout",
            "strategy_core_full_stack",
        ]
        usable = [c for c in experiment_cols if c in results.columns]
        candidate_mask = results[usable].fillna(False).astype(bool).any(axis=1) if usable else pd.Series(False, index=results.index)
        results[candidate_mask].to_csv(candidates_path, index=False, encoding=encoding)

    summary.to_csv(summary_path, index=False, encoding=encoding)
    errors.to_csv(errors_path, index=False, encoding=encoding)
    pd.DataFrame([meta.to_dict()]).to_csv(meta_csv_path, index=False, encoding=encoding)
    meta_json_path.write_text(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n============================================")
    print(" TrendFollowingAnalyzer - V1 Range Backtest")
    print("============================================")
    print(f"Range      : {meta.range_start} ~ {meta.range_end}")
    print(f"Top N      : {meta.top_n}")
    print(f"Calendar   : {meta.calendar_dates}")
    print(f"Universe   : loaded={meta.universe_dates_loaded} failed={meta.universe_dates_failed}")
    print(f"Tickers    : {meta.unique_tickers}")
    print(f"Rows       : {meta.rows:,}")
    print("Universe policy: POINT_IN_TIME_ONLY")
    print("Entry price     : signal-day close")
    print("Forward returns : D+5 / D+20 / D+60 close-to-close")
    print("Structure rules : EXPERIMENTAL / BACKTEST_ONLY")

    if not summary.empty:
        print("\n[STRATEGY SUMMARY - ALL MARKET]")
        cols = ["strategy", "horizon", "signal_count", "complete_count", "avg_return_pct", "median_return_pct", "win_rate_pct"]
        view = summary[summary["market"].eq("ALL")][cols]
        print(view.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    for path in [all_path, core_path, candidates_path, summary_path, errors_path, meta_csv_path, meta_json_path]:
        print(f"[DONE] {path}")


if __name__ == "__main__":
    main()
