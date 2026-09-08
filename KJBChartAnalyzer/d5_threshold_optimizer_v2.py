from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import median

import numpy as np
import pandas as pd

from d5_diagnostics import (
    RESULTS_ROOT,
    _latest_range_dir,
    _num,
    build_d5_strategy,
    load_events_with_market_context,
)
from d5_threshold_optimizer import metrics, _folds, _purge_train, _flatten, _mean_col


PARAM_SPACE = {
    "selection_min": [70.0, 72.0, 75.0, 78.0],
    "timing_min": [72.0, 75.0, 78.0, 80.0],
    "selection_weight": [0.35, 0.45, 0.55],
    "rs_hard": [90.0, 92.0, 95.0],
    "leader_soft": [78.0, 80.0, 82.0],
    "leader_hard": [86.0, 88.0, 90.0],
    "sector_soft": [76.0, 78.0, 80.0],
    "sector_hard": [84.0, 86.0, 88.0],
    "combo_rs_leader": [2.0, 3.0, 4.0],
    "combo_triple": [3.0, 4.0, 5.0],
    "overextension_max": [6.0, 8.0, 10.0],
    "d5_score_min": [68.0, 70.0, 72.0, 75.0],
    "daily_top_n": [1, 3, 5],
    # V2: market regime is no longer a hard filter. It only adjusts ranking score.
    "range_adjust": [0.0, 1.0, 2.0],
    "uptrend_adjust": [-1.0, 0.0, 1.0],
    "downtrend_adjust": [-4.0, -3.0, -2.0],
    "volatile_adjust": [-2.0, -1.0, 0.0],
}


BASELINE = {
    "selection_min": 70.0,
    "timing_min": 72.0,
    "selection_weight": 0.45,
    "rs_hard": 92.0,
    "leader_soft": 80.0,
    "leader_hard": 88.0,
    "sector_soft": 78.0,
    "sector_hard": 86.0,
    "combo_rs_leader": 3.0,
    "combo_triple": 4.0,
    "overextension_max": 8.0,
    "d5_score_min": 70.0,
    "daily_top_n": 3,
    "range_adjust": 0.0,
    "uptrend_adjust": 0.0,
    "downtrend_adjust": 0.0,
    "volatile_adjust": 0.0,
}


PARAMETER_KEYS = list(BASELINE.keys())


def _trial_key(params: dict) -> tuple:
    return tuple((k, params[k]) for k in sorted(params))


def generate_trials(max_trials: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    trials = [BASELINE.copy()]
    seen = {_trial_key(trials[0])}
    attempts = 0
    limit = max(1, int(max_trials))
    while len(trials) < limit and attempts < limit * 200:
        attempts += 1
        params = {key: rng.choice(values) for key, values in PARAM_SPACE.items()}
        if params["leader_hard"] <= params["leader_soft"]:
            continue
        if params["sector_hard"] <= params["sector_soft"]:
            continue
        key = _trial_key(params)
        if key in seen:
            continue
        seen.add(key)
        trials.append(params)
    return trials


def _regime_adjustment(frame: pd.DataFrame, params: dict) -> pd.Series:
    if "market_regime" not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype=float)

    regime = frame["market_regime"].astype(str).str.lower().str.strip()
    values = np.select(
        [
            regime.eq("range"),
            regime.eq("uptrend"),
            regime.eq("downtrend"),
            regime.eq("volatile"),
        ],
        [
            float(params["range_adjust"]),
            float(params["uptrend_adjust"]),
            float(params["downtrend_adjust"]),
            float(params["volatile_adjust"]),
        ],
        default=0.0,
    )
    return pd.Series(values, index=frame.index, dtype=float)


def apply_trial(frame: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Apply a D+5 candidate parameter set with soft market-regime scoring.

    V1 used regime as a hard include/exclude condition. V2 keeps every baseline
    CONFIRMED candidate eligible and only adjusts D+5 rank/threshold score by
    market regime. WATCH is still never promoted to CONFIRMED.
    """
    out = build_d5_strategy(
        frame,
        selection_weight=float(params["selection_weight"]),
        timing_weight=1.0 - float(params["selection_weight"]),
        rs_hard=float(params["rs_hard"]),
        leader_soft=float(params["leader_soft"]),
        leader_hard=float(params["leader_hard"]),
        sector_soft=float(params["sector_soft"]),
        sector_hard=float(params["sector_hard"]),
        rs_leader_combo_penalty=float(params["combo_rs_leader"]),
        triple_combo_penalty=float(params["combo_triple"]),
        overextension_max_exclusive=float(params["overextension_max"]),
        selection_min=float(params["selection_min"]),
        timing_min=float(params["timing_min"]),
        d5_score_min=float(params["d5_score_min"]),
    )

    adjustment = _regime_adjustment(out, params)
    out["market_regime_adjustment"] = adjustment.round(2)
    out["d5_optimizer_score"] = (
        _num(out, "d5_adjusted_score").fillna(0.0) + adjustment
    ).clip(0, 100).round(2)

    base_status = out.get("Status", pd.Series("WATCH", index=out.index)).astype(str)
    confirmed = (
        base_status.eq("CONFIRMED")
        & _num(out, "selection_score").ge(float(params["selection_min"]))
        & _num(out, "timing_score").ge(float(params["timing_min"]))
        & _num(out, "d5_optimizer_score").ge(float(params["d5_score_min"]))
        & _num(out, "overextension_penalty", 0.0)
        .fillna(0.0)
        .lt(float(params["overextension_max"]))
    )

    out["D5_Status_V2"] = np.select(
        [confirmed, base_status.eq("REJECTED")],
        ["D5_CONFIRMED", "D5_REJECTED"],
        default="D5_WATCH",
    )
    out["D5_Eligible"] = confirmed
    out["D5_Selected"] = False
    out["d5_optimized_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")

    if confirmed.any():
        rank = (
            out.loc[confirmed]
            .groupby("signal_date")["d5_optimizer_score"]
            .rank(method="first", ascending=False)
            .astype("Int64")
        )
        out.loc[confirmed, "d5_optimized_rank"] = rank
        selected = confirmed & _num(out, "d5_optimized_rank").le(
            int(params["daily_top_n"])
        )
        out.loc[selected, "D5_Selected"] = True

    return out


def _mode(values: list):
    if not values:
        return None
    return pd.Series(values).value_counts().index[0]


def recommend_from_folds(fold_rows: list[dict]) -> dict:
    """Aggregate train-only fold winners; do not choose parameters from OOS returns."""
    if not fold_rows:
        return BASELINE.copy()

    source = [row for row in fold_rows if row.get("train_objective") is not None]
    if not source:
        source = fold_rows

    recommended: dict = {}
    categorical = {"daily_top_n"}
    for key in PARAMETER_KEYS:
        values = [row[key] for row in source if key in row]
        if not values:
            recommended[key] = BASELINE[key]
        elif key in categorical:
            recommended[key] = _mode(values)
        else:
            recommended[key] = float(median([float(v) for v in values]))

    recommended["daily_top_n"] = int(recommended["daily_top_n"])
    if recommended["leader_hard"] <= recommended["leader_soft"]:
        recommended["leader_hard"] = max(
            recommended["leader_soft"] + 2.0, BASELINE["leader_hard"]
        )
    if recommended["sector_hard"] <= recommended["sector_soft"]:
        recommended["sector_hard"] = max(
            recommended["sector_soft"] + 2.0, BASELINE["sector_hard"]
        )
    return recommended


def _paired_folds(fold_df: pd.DataFrame) -> pd.DataFrame:
    if fold_df.empty:
        return fold_df.copy()
    required = ["test_avg_excess_D+5", "baseline_test_avg_excess_D+5"]
    if not all(col in fold_df.columns for col in required):
        return fold_df.iloc[0:0].copy()
    opt = pd.to_numeric(fold_df[required[0]], errors="coerce")
    base = pd.to_numeric(fold_df[required[1]], errors="coerce")
    return fold_df.loc[opt.notna() & base.notna()].copy()


def _parameter_stability(fold_df: pd.DataFrame) -> float:
    """Average modal share of train-selected parameters across folds."""
    if fold_df.empty:
        return 0.0
    shares: list[float] = []
    for key in PARAMETER_KEYS:
        if key not in fold_df.columns:
            continue
        values = fold_df[key].dropna()
        if values.empty:
            continue
        shares.append(float(values.value_counts(normalize=True).iloc[0]))
    return float(np.mean(shares)) if shares else 0.0


def _confidence(fold_df: pd.DataFrame) -> tuple[str, bool, dict]:
    """Confidence requires OOS improvement over baseline on comparable folds."""
    paired = _paired_folds(fold_df)
    paired_folds = int(len(paired))
    stability = _parameter_stability(fold_df)

    if paired_folds == 0:
        stats = {
            "paired_test_folds": 0,
            "positive_excess_fold_ratio": 0.0,
            "baseline_beat_ratio": 0.0,
            "mean_delta_test_avg_excess_D+5": np.nan,
            "mean_paired_test_avg_excess_D+5": np.nan,
            "parameter_stability": stability,
            "paired_oos_sample_count": 0,
        }
        return "PROVISIONAL", False, stats

    opt_excess = pd.to_numeric(paired["test_avg_excess_D+5"], errors="coerce")
    base_excess = pd.to_numeric(
        paired["baseline_test_avg_excess_D+5"], errors="coerce"
    )
    delta = opt_excess - base_excess
    positive_ratio = float((opt_excess > 0).mean())
    beat_ratio = float((delta > 0).mean())
    mean_delta = float(delta.mean())
    mean_excess = float(opt_excess.mean())
    oos_samples = int(
        pd.to_numeric(paired.get("test_sample_count", 0), errors="coerce")
        .fillna(0)
        .sum()
    )

    stats = {
        "paired_test_folds": paired_folds,
        "positive_excess_fold_ratio": positive_ratio,
        "baseline_beat_ratio": beat_ratio,
        "mean_delta_test_avg_excess_D+5": mean_delta,
        "mean_paired_test_avg_excess_D+5": mean_excess,
        "parameter_stability": stability,
        "paired_oos_sample_count": oos_samples,
    }

    # ROBUST: four comparable OOS years, baseline beaten in >=75%, stable parameters.
    if (
        paired_folds >= 4
        and mean_excess > 0
        and positive_ratio >= 0.75
        and mean_delta > 0
        and beat_ratio >= 0.75
        and stability >= 0.60
        and oos_samples >= 120
    ):
        return "ROBUST", True, stats

    # ACCEPTABLE: at least three comparable OOS years and actual mean improvement.
    if (
        paired_folds >= 3
        and mean_excess > 0
        and positive_ratio >= 0.60
        and mean_delta > 0
        and beat_ratio >= 0.50
        and oos_samples >= 90
    ):
        return "ACCEPTABLE", True, stats

    return "PROVISIONAL", False, stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KJB D+5 Threshold Optimizer V2 - soft regime + baseline-relative OOS"
    )
    parser.add_argument("--range-dir", default=None)
    parser.add_argument("--max-trials", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260908)
    parser.add_argument("--min-train-samples", type=int, default=150)
    parser.add_argument("--min-test-samples", type=int, default=30)
    parser.add_argument("--purge-bars", type=int, default=5)
    args = parser.parse_args()

    range_dir = Path(args.range_dir) if args.range_dir else _latest_range_dir(RESULTS_ROOT)
    events_path = range_dir / "chart_range_events.csv"
    events = load_events_with_market_context(range_dir, events_path)
    if "D+5" not in events.columns:
        raise ValueError("D+5 컬럼이 없습니다. forward-bars >= 5로 range를 먼저 실행하세요.")

    events = events[pd.to_datetime(events["signal_date"], errors="coerce").notna()].copy()
    events["year"] = pd.to_datetime(events["signal_date"]).dt.year.astype(int)

    trials = generate_trials(args.max_trials, args.seed)
    folds = _folds(events)
    trial_rows: list[dict] = []
    fold_rows: list[dict] = []

    print("=" * 78)
    print("KJB D+5 Threshold Optimizer V2")
    print("Soft Market Regime + Baseline-relative Purged Walk-forward")
    print("=" * 78)
    print("Range      :", range_dir)
    print("Trials     :", len(trials))
    print("Folds      :", len(folds))
    print("Purge bars :", args.purge_bars)

    for fold_no, (train_start, train_end, test_year) in enumerate(folds, start=1):
        raw_train = events[
            (events["year"] >= train_start) & (events["year"] <= train_end)
        ].copy()
        test = events[events["year"] == test_year].copy()
        train, purged_dates, purge_from = _purge_train(
            raw_train, test, args.purge_bars
        )

        best_params = None
        best_metrics = None

        for trial_no, params in enumerate(trials, start=1):
            scored = apply_trial(train, params)
            selected = scored[scored["D5_Selected"]]
            train_metrics = metrics(selected, min_samples=args.min_train_samples)
            if train_metrics is None:
                continue

            trial_row = {
                "fold": fold_no,
                "train_start": train_start,
                "train_end": train_end,
                "test_year": test_year,
                "trial": trial_no,
                "purged_train_dates": purged_dates,
            }
            trial_row.update(params)
            trial_row.update(_flatten("train", train_metrics))
            trial_rows.append(trial_row)

            if best_metrics is None or train_metrics["objective"] > best_metrics["objective"]:
                best_metrics = train_metrics
                best_params = params.copy()

        if best_params is None:
            print(f"[WARN] fold {fold_no}: 최소 train 표본 조건을 만족한 trial 없음")
            continue

        test_scored = apply_trial(test, best_params)
        test_selected = test_scored[test_scored["D5_Selected"]]
        test_metrics = metrics(test_selected, min_samples=args.min_test_samples)

        baseline_scored = apply_trial(test, BASELINE)
        baseline_selected = baseline_scored[baseline_scored["D5_Selected"]]
        baseline_metrics = metrics(
            baseline_selected, min_samples=args.min_test_samples
        )

        fold_row = {
            "fold": fold_no,
            "train_start": train_start,
            "train_end": train_end,
            "test_year": test_year,
            "purge_bars": int(args.purge_bars),
            "purged_train_dates": purged_dates,
            "purge_from": purge_from,
            "train_rows_before_purge": int(len(raw_train)),
            "train_rows_after_purge": int(len(train)),
            "test_rows": int(len(test)),
        }
        fold_row.update(best_params)
        fold_row.update(_flatten("train", best_metrics))
        fold_row.update(_flatten("test", test_metrics))
        fold_row.update(_flatten("baseline_test", baseline_metrics))

        if test_metrics and baseline_metrics:
            fold_row["delta_test_avg_D+5"] = (
                test_metrics["avg_D+5"] - baseline_metrics["avg_D+5"]
            )
            fold_row["delta_test_avg_excess_D+5"] = (
                test_metrics["avg_excess_D+5"]
                - baseline_metrics["avg_excess_D+5"]
            )
            fold_row["delta_test_win_rate_D+5"] = (
                test_metrics["win_rate_D+5"] - baseline_metrics["win_rate_D+5"]
            )

        fold_rows.append(fold_row)

        if test_metrics:
            opt_text = (
                f"opt D5={test_metrics['avg_D+5']*100:.2f}% "
                f"excess={test_metrics['avg_excess_D+5']*100:.2f}% "
                f"n={test_metrics['sample_count']}"
            )
        else:
            opt_text = "opt=n/a"
        if baseline_metrics:
            base_text = (
                f"baseline excess={baseline_metrics['avg_excess_D+5']*100:.2f}% "
                f"n={baseline_metrics['sample_count']}"
            )
        else:
            base_text = "baseline=n/a"
        print(
            f"[Fold {fold_no}] {train_start}-{train_end} -> {test_year} "
            f"| purge={purged_dates} | {opt_text} | {base_text}"
        )

    if not fold_rows:
        raise RuntimeError("유효한 walk-forward fold가 없습니다.")

    fold_df = pd.DataFrame(fold_rows)
    recommended = recommend_from_folds(fold_rows)

    optimized = apply_trial(events, recommended)
    optimized_selected = optimized[optimized["D5_Selected"]]
    all_metrics = metrics(optimized_selected, min_samples=1)

    baseline_all = apply_trial(events, BASELINE)
    baseline_all_metrics = metrics(
        baseline_all[baseline_all["D5_Selected"]], min_samples=1
    )

    trial_df = (
        pd.DataFrame(trial_rows).sort_values(
            ["fold", "train_objective"], ascending=[True, False]
        )
        if trial_rows
        else pd.DataFrame()
    )

    confidence, eligible, conf_stats = _confidence(fold_df)
    paired = _paired_folds(fold_df)

    summary = pd.DataFrame([{
        **recommended,
        **_flatten("all", all_metrics),
        **_flatten("baseline_all", baseline_all_metrics),
        "walkforward_folds": int(len(fold_df)),
        "optimizer_valid_test_folds": int(
            pd.to_numeric(fold_df.get("test_avg_D+5"), errors="coerce")
            .notna()
            .sum()
        ),
        "paired_test_folds": int(len(paired)),
        "purge_bars": int(args.purge_bars),
        "recommendation_confidence": confidence,
        "eligible_for_application": bool(eligible),
        **conf_stats,
        # The following means are deliberately calculated only on paired folds.
        "mean_test_avg_D+5": _mean_col(paired, "test_avg_D+5"),
        "mean_test_median_D+5": _mean_col(paired, "test_median_D+5"),
        "mean_test_win_rate_D+5": _mean_col(paired, "test_win_rate_D+5"),
        "mean_test_avg_excess_D+5": _mean_col(paired, "test_avg_excess_D+5"),
        "mean_baseline_test_avg_D+5": _mean_col(
            paired, "baseline_test_avg_D+5"
        ),
        "mean_baseline_test_avg_excess_D+5": _mean_col(
            paired, "baseline_test_avg_excess_D+5"
        ),
        "mean_delta_test_avg_D+5": _mean_col(paired, "delta_test_avg_D+5"),
        "mean_delta_test_avg_excess_D+5": _mean_col(
            paired, "delta_test_avg_excess_D+5"
        ),
        "mean_delta_test_win_rate_D+5": _mean_col(
            paired, "delta_test_win_rate_D+5"
        ),
    }])

    trials_path = range_dir / "kjb_d5_optimizer_v2_trials.csv"
    walk_path = range_dir / "kjb_d5_walkforward_v2.csv"
    best_path = range_dir / "kjb_d5_optimizer_v2_best.json"
    summary_path = range_dir / "kjb_d5_optimizer_v2_summary.csv"
    optimized_path = range_dir / "chart_range_events_d5_optimized_v2.csv"

    if not trial_df.empty:
        trial_df.to_csv(trials_path, index=False, encoding="utf-8-sig")
    fold_df.to_csv(walk_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    optimized.drop(columns=["year"], errors="ignore").to_csv(
        optimized_path, index=False, encoding="utf-8-sig"
    )

    best_path.write_text(
        json.dumps(
            {
                "optimizer_version": "V2",
                "recommended_params": recommended,
                "recommendation_confidence": confidence,
                "eligible_for_application": bool(eligible),
                "confidence_stats": conf_stats,
                "purge_bars": int(args.purge_bars),
                "all_data_metrics_for_reference_only": all_metrics,
                "baseline_all_data_metrics_for_reference_only": baseline_all_metrics,
                "note": (
                    "V2 uses market regime only as a soft D+5 ranking adjustment. "
                    "Confidence is based on paired out-of-sample folds and requires "
                    "positive mean excess improvement versus baseline before application."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n[Recommended V2 parameters]")
    print(json.dumps(recommended, ensure_ascii=False, indent=2))
    print("\n[Paired Walk-forward OOS]")
    for col in [
        "mean_test_avg_D+5",
        "mean_baseline_test_avg_D+5",
        "mean_delta_test_avg_D+5",
        "mean_test_avg_excess_D+5",
        "mean_baseline_test_avg_excess_D+5",
        "mean_delta_test_avg_excess_D+5",
    ]:
        value = summary.iloc[0][col]
        print(
            f"{col:39s}: {value*100:.2f}%"
            if pd.notna(value)
            else f"{col:39s}: -"
        )
    print(f"paired_test_folds                       : {conf_stats['paired_test_folds']}")
    print(f"baseline_beat_ratio                     : {conf_stats['baseline_beat_ratio']*100:.1f}%")
    print(f"positive_excess_fold_ratio              : {conf_stats['positive_excess_fold_ratio']*100:.1f}%")
    print(f"parameter_stability                     : {conf_stats['parameter_stability']*100:.1f}%")
    print(f"confidence                              : {confidence}")
    print(f"eligible_for_application                : {eligible}")

    print("\n[완료]")
    print("Trials       :", trials_path)
    print("Walk-forward :", walk_path)
    print("Best params  :", best_path)
    print("Summary      :", summary_path)
    print("Optimized evt:", optimized_path)


if __name__ == "__main__":
    main()
