from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
for p in (REPO_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ThresholdOptimization import ThresholdOptimizer  # noqa: E402
from optimization import DynamicThresholdAdapter  # noqa: E402


CLOSE_MFE_D20 = "close_MFE_D20"
CLOSE_MAE_D20 = "close_MAE_D20"
CLOSE_EXCURSION_RATIO_D20 = "close_excursion_ratio_D20"


def _latest_range_file() -> Path:
    files = list((BASE_DIR / "results").glob("range_*/dynamic_range_events.csv"))
    if not files:
        raise FileNotFoundError("No dynamic_range_events.csv found. Run run_dynamic_range.bat first.")
    return max(files, key=lambda p: p.stat().st_mtime)


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def add_close_path_excursions(df: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    """Add reproducible D+N close-path excursion metrics.

    Dynamic range files already contain direction-adjusted D+1..D+N close returns.
    We intentionally call these *close* MFE/MAE so they are not confused with true
    intraday high/low MFE/MAE. They are useful for threshold optimization without
    re-fetching market data and remain reproducible from the range CSV alone.

    - close_MFE_D20: best direction-adjusted close return from D+1..D+20, floored at 0.
    - close_MAE_D20: worst direction-adjusted close return from D+1..D+20, capped at 0.
    - close_excursion_ratio_D20: MFE / max(|MAE|, 0.5%), clipped to [0, 10].

    The denominator floor and cap keep nearly-zero MAE observations from dominating
    fold-level z-scores.
    """
    out = df.copy()
    cols = [f"D+{h}" for h in range(1, int(horizon) + 1)]
    missing = [c for c in cols if c not in out.columns]
    if missing:
        raise ValueError(
            "Dynamic optimizer requires D+1..D+20 path columns; missing: "
            + ", ".join(missing[:5])
            + (" ..." if len(missing) > 5 else "")
        )

    path = out[cols].apply(pd.to_numeric, errors="coerce")
    available = path.notna().any(axis=1)
    mfe = path.max(axis=1, skipna=True).clip(lower=0.0).where(available)
    mae = path.min(axis=1, skipna=True).clip(upper=0.0).where(available)
    denominator = mae.abs().clip(lower=0.005)
    ratio = (mfe / denominator).clip(lower=0.0, upper=10.0).where(available)

    suffix = int(horizon)
    out[f"close_MFE_D{suffix}"] = mfe
    out[f"close_MAE_D{suffix}"] = mae
    out[f"close_excursion_ratio_D{suffix}"] = ratio
    return out


def _apply_stage_overrides(config: dict, stage: int) -> dict:
    """Merge stage-specific WFO settings into the common optimizer config."""
    out = copy.deepcopy(config or {})
    stage_key = f"stage{int(stage)}"
    overrides = (out.get("stage_overrides", {}) or {}).get(stage_key, {}) or {}
    if overrides:
        optimizer = dict(out.get("optimizer", {}) or {})
        optimizer.update(overrides)
        out["optimizer"] = optimizer
    return out


def _performance_gate(row: pd.Series, gate_cfg: dict) -> tuple[bool, list[str]]:
    """Check absolute OOS performance floors after statistical stability grading.

    The ThresholdOptimization engine grades statistical evidence (fold coverage,
    plateau and dispersion). DynamicChartAnalyzer additionally requires absolute
    return quality before a threshold may be applied. This prevents a stable but
    consistently weak threshold from being marked deployable.
    """
    if not bool((gate_cfg or {}).get("enabled", False)):
        return True, []

    checks = (
        ("mean_median_return", "min_mean_median_return", "median_return"),
        ("mean_win_rate", "min_mean_win_rate", "win_rate"),
        ("mean_p25_return", "min_mean_p25_return", "p25_return"),
    )
    failures: list[str] = []
    for column, config_key, label in checks:
        if config_key not in gate_cfg:
            continue
        minimum = float(gate_cfg[config_key])
        value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
        if pd.isna(value):
            failures.append(f"{label}=missing (required>={minimum:g})")
        elif float(value) < minimum:
            failures.append(f"{label}={float(value):.6g} < {minimum:g}")
    return len(failures) == 0, failures


def _apply_performance_gate(result, optimizer: ThresholdOptimizer, df: pd.DataFrame, active_cfg: dict):
    """Apply Dynamic-only absolute performance gate and reselect the candidate.

    Statistical recommendation_quality is preserved. Application eligibility is
    stricter: ACCEPTABLE/ROBUST *and* the absolute performance gate must pass.

    If no threshold passes both requirements, prefer an evaluable candidate that
    still passes the absolute performance gate. This makes the provisional output
    useful for research while keeping automatic application disabled.
    """
    gate_cfg = dict((active_cfg or {}).get("application_performance_gate", {}) or {})
    if not bool(gate_cfg.get("enabled", False)):
        return result

    trials = result.all_trials.copy()
    trials["statistically_eligible"] = (
        trials["eligible_for_application"].fillna(False).astype(bool)
    )

    gate_results = trials.apply(lambda row: _performance_gate(row, gate_cfg), axis=1)
    trials["performance_gate_pass"] = [bool(x[0]) for x in gate_results]
    trials["performance_gate_failures"] = ["; ".join(x[1]) for x in gate_results]
    trials["eligible_for_application"] = (
        trials["statistically_eligible"] & trials["performance_gate_pass"]
    )

    evaluable_mask = trials["final_score"].notna() & (trials["valid_folds"] >= 1)
    strict = trials[
        evaluable_mask
        & (trials["valid_folds"] >= optimizer.min_valid_folds)
        & trials["eligible_for_application"].fillna(False).astype(bool)
    ].copy()

    used_performance_gate_fallback = strict.empty
    used_gate_failure_fallback = False
    if used_performance_gate_fallback:
        performance_pass = trials[
            evaluable_mask & trials["performance_gate_pass"].fillna(False).astype(bool)
        ].copy()
        if not performance_pass.empty:
            candidate_pool = performance_pass
        else:
            candidate_pool = trials[evaluable_mask].copy()
            used_gate_failure_fallback = True
        if candidate_pool.empty:
            raise ValueError("Performance gate left no evaluable Dynamic threshold candidate.")
    else:
        candidate_pool = strict

    candidate_pool = candidate_pool.sort_values(
        "final_score", ascending=False, na_position="last"
    ).reset_index(drop=True)
    best = candidate_pool.iloc[0]
    space = optimizer.adapter.parameter_space(optimizer.config)
    recommended = {
        name: best[name].item() if hasattr(best[name], "item") else best[name]
        for name in space
    }
    quality = str(best.get("recommendation_quality", "PROVISIONAL"))
    gate_pass = bool(best.get("performance_gate_pass", False))
    statistically_eligible = bool(best.get("statistically_eligible", False))
    eligible = (
        statistically_eligible
        and gate_pass
        and not used_performance_gate_fallback
    )

    prepared = optimizer._prepare(df)
    folds = optimizer.splitter.split(prepared[optimizer.adapter.date_column])
    comparison = optimizer._comparison(
        prepared,
        folds,
        recommended,
        quality=quality,
        eligible=eligible,
    )

    result.recommended_params = recommended
    result.recommended_config = optimizer.adapter.export_config(recommended)
    result.recommendation_quality = quality
    result.eligible_for_application = eligible
    result.all_trials = trials.sort_values(
        "final_score", ascending=False, na_position="last"
    ).reset_index(drop=True)
    result.current_vs_optimized = comparison
    result.top_configs = candidate_pool.head(optimizer.top_n).copy()

    stability_cols = list(space) + [
        "valid_folds",
        "total_folds",
        "fold_coverage",
        "mean_validation_objective",
        "std_validation_objective",
        "robust_score",
        "mean_median_return",
        "mean_win_rate",
        "mean_p25_return",
        "plateau_neighbor_count",
        "plateau_neighbor_mean",
        "plateau_drop",
        "current_distance",
        "final_score",
        "recommendation_quality",
        "statistically_eligible",
        "performance_gate_pass",
        "performance_gate_failures",
        "eligible_for_application",
    ]
    result.stability_report = candidate_pool[
        [c for c in stability_cols if c in candidate_pool.columns]
    ].head(min(20, len(candidate_pool))).copy()

    diagnostics = dict(result.recommendation_diagnostics or {})
    diagnostics.update(
        {
            # Refresh every "best" field after the performance gate possibly
            # reselects a different threshold candidate.
            "best_valid_folds": int(best.get("valid_folds", 0) or 0),
            "best_fold_coverage": float(best.get("fold_coverage", 0.0) or 0.0),
            "best_std_validation_objective": best.get("std_validation_objective"),
            "best_plateau_neighbor_count": int(
                best.get("plateau_neighbor_count", 0) or 0
            ),
            "best_plateau_drop": best.get("plateau_drop"),
            "best_statistically_eligible": statistically_eligible,
            "performance_gate_enabled": True,
            "performance_gate_thresholds": {
                "min_mean_median_return": gate_cfg.get("min_mean_median_return"),
                "min_mean_win_rate": gate_cfg.get("min_mean_win_rate"),
                "min_mean_p25_return": gate_cfg.get("min_mean_p25_return"),
            },
            "best_performance_gate_pass": gate_pass,
            "best_performance_gate_failures": str(
                best.get("performance_gate_failures", "") or ""
            ),
            "best_mean_median_return": best.get("mean_median_return"),
            "best_mean_win_rate": best.get("mean_win_rate"),
            "best_mean_p25_return": best.get("mean_p25_return"),
            "used_performance_gate_fallback": used_performance_gate_fallback,
            "used_gate_failure_fallback": used_gate_failure_fallback,
            "used_provisional_fallback": bool(
                diagnostics.get("used_provisional_fallback", False)
                or used_performance_gate_fallback
            ),
        }
    )
    result.recommendation_diagnostics = diagnostics
    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Dynamic V2.3 stage-aware purged walk-forward threshold optimizer")
    p.add_argument("--range-file")
    p.add_argument("--optimizer-config", default="threshold_optimizer.yaml")
    p.add_argument("--stage", type=int, choices=[1, 2, 3], default=3)
    p.add_argument("--current-confirmed-score", type=float, default=70.0)
    p.add_argument("--out")
    args = p.parse_args()

    range_file = _resolve(args.range_file, _latest_range_file())
    base_optimizer_cfg = yaml.safe_load(
        _resolve(args.optimizer_config, BASE_DIR / "threshold_optimizer.yaml").read_text(encoding="utf-8")
    ) or {}
    optimizer_cfg = _apply_stage_overrides(base_optimizer_cfg, args.stage)

    df = pd.read_csv(range_file, encoding="utf-8-sig", dtype={"ticker": str}, low_memory=False)
    df = add_close_path_excursions(df, horizon=20)

    active_cfg = optimizer_cfg.get("optimizer", {}) or {}
    gate_cfg = active_cfg.get("application_performance_gate", {}) or {}
    print(f"[INFO] optimizer input: {range_file}")
    print(f"[INFO] Dynamic V2.3 target stage: {args.stage}")
    print(
        "[INFO] D+20 risk metrics: "
        f"{CLOSE_MAE_D20} / {CLOSE_MFE_D20} / {CLOSE_EXCURSION_RATIO_D20}"
    )
    print("[INFO] Excursions use D+1..D+20 direction-adjusted closes, not intraday high/low.")
    print(
        "[INFO] WFO: "
        f"train>={active_cfg.get('min_train_trading_days')}d, "
        f"validation={active_cfg.get('validation_trading_days')}d, "
        f"step={active_cfg.get('step_trading_days')}d, "
        f"purge={active_cfg.get('purge_trading_days')}d, "
        f"validation min samples={active_cfg.get('min_samples')}"
    )
    if bool(gate_cfg.get("enabled", False)):
        print(
            "[INFO] Application performance gate: "
            f"median>={gate_cfg.get('min_mean_median_return')}, "
            f"win_rate>={gate_cfg.get('min_mean_win_rate')}%, "
            f"P25>={gate_cfg.get('min_mean_p25_return')}"
        )

    out_dir = _resolve(args.out, range_file.parent / "optimizer")
    stage_dir = out_dir / f"stage{args.stage}"

    adapter = DynamicThresholdAdapter(
        phase="confirmed",
        analyzer_config={"confirmed_score": float(args.current_confirmed_score), "target_stage": int(args.stage)},
    )
    optimizer = ThresholdOptimizer(adapter, optimizer_cfg)
    result = optimizer.run(df)
    result = _apply_performance_gate(result, optimizer, df, active_cfg)
    paths = result.write(stage_dir / "confirmed")
    result.current_vs_optimized.to_csv(stage_dir / "current_vs_optimized.csv", index=False, encoding="utf-8-sig")

    eligible_path = stage_dir / "recommended_thresholds.yaml"
    provisional_path = stage_dir / "provisional_thresholds.yaml"
    eligible_payload = result.recommended_config if result.eligible_for_application else {}
    provisional_payload = {} if result.eligible_for_application else result.recommended_config
    eligible_path.write_text(yaml.safe_dump(eligible_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    provisional_path.write_text(yaml.safe_dump(provisional_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    diagnostics = result.recommendation_diagnostics or {}
    print("\n============================================")
    print(" Dynamic V2.3 Stage Threshold Optimizer complete")
    print("============================================")
    print(f"Input        : {range_file}")
    print(f"Target stage : {args.stage}")
    print(f"Output       : {stage_dir}")
    print(f"Candidate    : {result.recommended_params}")
    print(f"Quality      : {result.recommendation_quality}")
    if diagnostics.get("performance_gate_enabled"):
        print(
            "Perf Gate    : "
            + ("PASS" if diagnostics.get("best_performance_gate_pass") else "FAIL")
        )
        if diagnostics.get("best_performance_gate_failures"):
            print(f"Gate reason  : {diagnostics.get('best_performance_gate_failures')}")
    print(f"Application  : {'ELIGIBLE' if result.eligible_for_application else 'NOT ELIGIBLE'}")
    print(f"Summary      : {paths['recommendation_summary']}")
    print(f"Config       : {eligible_path if result.eligible_for_application else provisional_path}")
    print("Lecture RSI/MACD/Ichimoku timing and fixed 2:6:2 allocation are not optimized here.")
    print("Only one Stage quality threshold is optimized per run.")


if __name__ == "__main__":
    main()
