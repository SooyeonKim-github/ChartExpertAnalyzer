from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
for p in (REPO_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import DEFAULT_CONFIG  # noqa: E402
from optimization import SwingThresholdAdapter, SwingThresholdOptimizer  # noqa: E402


def _latest_optimizer_input() -> Path:
    manifests = list(
        (BASE_DIR / "results").glob("range_*/threshold_input/manifest.csv")
    )
    if manifests:
        return max(manifests, key=lambda p: p.stat().st_mtime)

    files = list((BASE_DIR / "results").glob("range_*/range_all_results.csv"))
    if not files:
        raise FileNotFoundError(
            "No Swing threshold_input/manifest.csv or range_all_results.csv found. "
            "Run the range analyzer / threshold exporter first."
        )
    return max(files, key=lambda p: p.stat().st_mtime)


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def _resolve_optimizer_input(value: str | None) -> Path:
    if not value:
        return _latest_optimizer_input()

    raw = Path(value)
    if raw.is_absolute():
        return raw

    direct = BASE_DIR / raw
    if direct.exists():
        return direct

    under_results = BASE_DIR / "results" / raw
    if under_results.exists():
        return under_results

    if raw.name.startswith("range_") and len(raw.parts) == 1:
        return under_results
    return direct


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        encoding="utf-8-sig",
        dtype={"Ticker": str},
        low_memory=False,
    )


def _load_manifest(manifest_path: Path) -> pd.DataFrame:
    manifest = _read_csv(manifest_path)
    if "file" not in manifest.columns:
        raise ValueError(f"manifest missing 'file' column: {manifest_path}")

    parts: list[pd.DataFrame] = []
    for name in manifest["file"].dropna().astype(str):
        part_path = manifest_path.parent / name
        if not part_path.exists():
            raise FileNotFoundError(f"threshold shard not found: {part_path}")
        parts.append(_read_csv(part_path))

    if not parts:
        raise ValueError(f"threshold manifest contains no data parts: {manifest_path}")
    return pd.concat(parts, ignore_index=True, sort=False)


def _load_optimizer_input(path: Path) -> tuple[pd.DataFrame, Path]:
    path = path.resolve()

    if path.is_dir():
        if path.name == "threshold_input":
            manifest = path / "manifest.csv"
            if not manifest.exists():
                raise FileNotFoundError(f"manifest not found: {manifest}")
            return _load_manifest(manifest), path.parent

        threshold_manifest = path / "threshold_input" / "manifest.csv"
        if threshold_manifest.exists():
            return _load_manifest(threshold_manifest), path

        full_range = path / "range_all_results.csv"
        if full_range.exists():
            return _read_csv(full_range), path

        raise FileNotFoundError(
            f"No threshold_input/manifest.csv or range_all_results.csv under: {path}"
        )

    if not path.exists():
        raise FileNotFoundError(
            f"Optimizer input not found: {path}\n"
            "Tip: enter only a range folder name such as range_20210101_20260901, "
            "or press Enter to use the latest exported threshold_input."
        )

    if path.name == "manifest.csv" and path.parent.name == "threshold_input":
        return _load_manifest(path), path.parent.parent

    if path.name.startswith("threshold_input_part_") and path.suffix.lower() == ".csv":
        return _read_csv(path), path.parent.parent

    if path.suffix.lower() == ".csv":
        return _read_csv(path), path.parent

    raise ValueError(f"Unsupported optimizer input: {path}")


def _parse_actual_date(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    ymd = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    fallback = pd.to_datetime(text, errors="coerce")
    return ymd.fillna(fallback).dt.normalize()


def _split_development_holdout(
    df: pd.DataFrame,
    optimizer_cfg: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if "Actual_Date" not in df.columns:
        raise ValueError("Actual_Date column is required for development/holdout split")

    ecfg = optimizer_cfg.get("evaluation", {}) or {}
    development_end = pd.Timestamp(ecfg.get("development_end", "2025-12-31"))
    holdout_start = pd.Timestamp(ecfg.get("holdout_start", "2026-01-01"))
    purge_days = int(ecfg.get("holdout_purge_trading_days", 20))

    if holdout_start <= development_end and holdout_start.year < development_end.year:
        raise ValueError("holdout_start must be after the development period")

    frame = df.copy()
    frame["Actual_Date"] = _parse_actual_date(frame["Actual_Date"])
    frame = frame[frame["Actual_Date"].notna()].copy()

    pre_holdout_dates = sorted(
        d for d in frame.loc[
            (frame["Actual_Date"] <= development_end)
            & (frame["Actual_Date"] < holdout_start),
            "Actual_Date",
        ].dropna().unique()
    )
    if len(pre_holdout_dates) <= purge_days:
        raise ValueError(
            "Not enough development trading dates before holdout after boundary purge"
        )

    if purge_days > 0:
        development_dates = pre_holdout_dates[:-purge_days]
        purged_dates = pre_holdout_dates[-purge_days:]
    else:
        development_dates = pre_holdout_dates
        purged_dates = []

    development_date_set = set(development_dates)
    development = frame[frame["Actual_Date"].isin(development_date_set)].copy()
    holdout = frame[frame["Actual_Date"] >= holdout_start].copy()

    if development.empty:
        raise ValueError("Development split is empty")
    if holdout.empty:
        raise ValueError("Final holdout split is empty")

    split_info = {
        "configured_development_end": development_end.date().isoformat(),
        "configured_holdout_start": holdout_start.date().isoformat(),
        "holdout_purge_trading_days": purge_days,
        "actual_development_start": development["Actual_Date"].min().date().isoformat(),
        "actual_development_end": development["Actual_Date"].max().date().isoformat(),
        "actual_holdout_start": holdout["Actual_Date"].min().date().isoformat(),
        "actual_holdout_end": holdout["Actual_Date"].max().date().isoformat(),
        "development_rows": int(len(development)),
        "holdout_rows": int(len(holdout)),
        "purged_boundary_start": (
            pd.Timestamp(purged_dates[0]).date().isoformat() if purged_dates else None
        ),
        "purged_boundary_end": (
            pd.Timestamp(purged_dates[-1]).date().isoformat() if purged_dates else None
        ),
    }
    return development, holdout, split_info


def _holdout_comparison(
    optimizer: SwingThresholdOptimizer,
    adapter: SwingThresholdAdapter,
    holdout: pd.DataFrame,
    recommended_params: dict,
    optimizer_cfg: dict,
) -> tuple[pd.DataFrame, dict]:
    ecfg = optimizer_cfg.get("evaluation", {}) or {}
    min_samples = int(ecfg.get("holdout_min_samples", 30))
    min_unique_dates = int(ecfg.get("holdout_min_unique_dates", 15))

    current_params = adapter.current_parameters()
    candidates = [
        ("CURRENT", current_params),
        ("OPTIMIZED", recommended_params),
    ]

    rows: list[dict] = []
    metrics_by_name: dict[str, dict] = {}
    for name, params in candidates:
        metrics = optimizer.evaluate_parameters(holdout, params)
        sample_valid = (
            int(metrics.get("count") or 0) >= min_samples
            and int(metrics.get("unique_dates") or 0) >= min_unique_dates
        )
        row = {
            "candidate": name,
            "entry_score": params.get("entry_score"),
            "max_entry_channel_position": params.get("max_entry_channel_position"),
            **metrics,
            "holdout_sample_valid": bool(sample_valid),
        }
        rows.append(row)
        metrics_by_name[name] = row

    comparison = pd.DataFrame(rows)
    current = metrics_by_name["CURRENT"]
    optimized = metrics_by_name["OPTIMIZED"]
    deltas: dict[str, float] = {}
    for key in optimizer.aggregate_metric_names:
        a = current.get(key)
        b = optimized.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            deltas[key] = float(b) - float(a)

    summary = {
        "holdout_min_samples": min_samples,
        "holdout_min_unique_dates": min_unique_dates,
        "current_parameters": current_params,
        "recommended_parameters": recommended_params,
        "current_holdout_sample_valid": bool(current["holdout_sample_valid"]),
        "optimized_holdout_sample_valid": bool(optimized["holdout_sample_valid"]),
        "both_holdout_samples_valid": bool(
            current["holdout_sample_valid"] and optimized["holdout_sample_valid"]
        ),
        "optimized_minus_current": deltas,
        "note": (
            "Holdout metrics are diagnostic only. 2026 data is never used to select "
            "the recommended parameters."
        ),
    }
    return comparison, summary


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "Swing Threshold Optimizer V2.1: 2D threshold search on development data "
            "plus a strictly isolated 2026 final holdout"
        )
    )
    p.add_argument(
        "--range-file",
        help=(
            "Accepts a bare range folder name, range_all_results.csv, range directory, "
            "threshold_input directory, or manifest.csv."
        ),
    )
    p.add_argument("--optimizer-config", default="threshold_optimizer.yaml")
    p.add_argument("--out")
    args = p.parse_args()

    input_path = _resolve_optimizer_input(args.range_file)
    optimizer_cfg = yaml.safe_load(
        _resolve_path(
            args.optimizer_config, BASE_DIR / "threshold_optimizer.yaml"
        ).read_text(encoding="utf-8")
    ) or {}

    df, range_dir = _load_optimizer_input(input_path)
    development, holdout, split_info = _split_development_holdout(df, optimizer_cfg)

    print(f"[INFO] optimizer input       : {input_path}")
    print(f"[INFO] loaded rows           : {len(df):,}")
    print(
        f"[INFO] development          : {split_info['actual_development_start']} ~ "
        f"{split_info['actual_development_end']} ({len(development):,} rows)"
    )
    print(
        f"[INFO] boundary purge       : {split_info['purged_boundary_start']} ~ "
        f"{split_info['purged_boundary_end']} "
        f"({split_info['holdout_purge_trading_days']} trading days)"
    )
    print(
        f"[INFO] final holdout        : {split_info['actual_holdout_start']} ~ "
        f"{split_info['actual_holdout_end']} ({len(holdout):,} rows)"
    )

    out_dir = _resolve_path(args.out, range_dir / "optimizer_v2_1")
    adapter = SwingThresholdAdapter(
        phase="confirmed",
        analyzer_config=DEFAULT_CONFIG.to_dict(),
    )
    optimizer = SwingThresholdOptimizer(adapter, optimizer_cfg)

    # Threshold selection sees development data only.
    result = optimizer.run(development)
    paths = result.write(out_dir / "development" / "confirmed")
    result.current_vs_optimized.to_csv(
        out_dir / "development_current_vs_optimized.csv",
        index=False,
        encoding="utf-8-sig",
    )

    eligible_path = out_dir / "recommended_thresholds.yaml"
    provisional_path = out_dir / "provisional_thresholds.yaml"
    if result.eligible_for_application:
        eligible_payload = result.recommended_config
        provisional_payload = {}
    else:
        eligible_payload = {}
        provisional_payload = result.recommended_config

    eligible_path.write_text(
        yaml.safe_dump(eligible_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    provisional_path.write_text(
        yaml.safe_dump(provisional_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # Evaluate fixed current/recommended parameters on 2026 without re-optimizing.
    holdout_comparison, holdout_summary = _holdout_comparison(
        optimizer,
        adapter,
        holdout,
        result.recommended_params,
        optimizer_cfg,
    )
    holdout_comparison_path = out_dir / "final_holdout_comparison.csv"
    holdout_comparison.to_csv(
        holdout_comparison_path,
        index=False,
        encoding="utf-8-sig",
    )

    summary_payload = {
        "split": split_info,
        "walk_forward_recommendation_quality": result.recommendation_quality,
        "eligible_for_holdout_review": bool(result.eligible_for_application),
        "recommended_params": result.recommended_params,
        "holdout": holdout_summary,
        "production_application_ready": False,
        "production_note": (
            "Review final_holdout_comparison.csv before applying thresholds to config.py."
        ),
    }
    holdout_summary_path = out_dir / "final_holdout_summary.yaml"
    holdout_summary_path.write_text(
        yaml.safe_dump(summary_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print("\n============================================")
    print(" Swing Threshold Optimizer V2.1 complete")
    print("============================================")
    print(f"Output             : {out_dir}")
    print(f"Candidate          : {result.recommended_params}")
    print(f"WF Quality         : {result.recommendation_quality}")
    print(
        f"Holdout Review     : "
        f"{'ELIGIBLE' if result.eligible_for_application else 'NOT ELIGIBLE'}"
    )
    print(f"Development Summary: {paths['recommendation_summary']}")
    print(f"Holdout Comparison : {holdout_comparison_path}")
    print(f"Holdout Summary    : {holdout_summary_path}")
    print("NOTE: 2026 holdout is evaluation-only and never participates in threshold search.")


if __name__ == "__main__":
    main()
