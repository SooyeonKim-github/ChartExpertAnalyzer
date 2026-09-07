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
    "regime": ["all", "uptrend+range", "range", "uptrend"],
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
    "regime": "all",
}


def _trial_key(p: dict) -> tuple:
    return tuple((k, p[k]) for k in sorted(p))


def generate_trials(max_trials: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    trials = [BASELINE.copy()]
    seen = {_trial_key(trials[0])}
    attempts = 0
    while len(trials) < max(1, int(max_trials)) and attempts < max_trials * 100:
        attempts += 1
        p = {k: rng.choice(v) for k, v in PARAM_SPACE.items()}
        if p["leader_hard"] <= p["leader_soft"] or p["sector_hard"] <= p["sector_soft"]:
            continue
        key = _trial_key(p)
        if key in seen:
            continue
        seen.add(key)
        trials.append(p)
    return trials


def _regime_filter(frame: pd.DataFrame, regime: str) -> pd.Series:
    if regime == "all" or "market_regime" not in frame.columns:
        return pd.Series(True, index=frame.index)
    x = frame["market_regime"].astype(str).str.lower()
    if regime == "uptrend+range":
        return x.isin(["uptrend", "range"])
    return x.eq(regime)


def apply_trial(frame: pd.DataFrame, p: dict) -> pd.DataFrame:
    out = build_d5_strategy(
        frame,
        selection_weight=float(p["selection_weight"]),
        timing_weight=1.0 - float(p["selection_weight"]),
        rs_hard=float(p["rs_hard"]),
        leader_soft=float(p["leader_soft"]),
        leader_hard=float(p["leader_hard"]),
        sector_soft=float(p["sector_soft"]),
        sector_hard=float(p["sector_hard"]),
        rs_leader_combo_penalty=float(p["combo_rs_leader"]),
        triple_combo_penalty=float(p["combo_triple"]),
        overextension_max_exclusive=float(p["overextension_max"]),
        selection_min=float(p["selection_min"]),
        timing_min=float(p["timing_min"]),
        d5_score_min=float(p["d5_score_min"]),
    )
    eligible = out["D5_Status"].eq("D5_CONFIRMED") & _regime_filter(out, str(p["regime"]))
    out["D5_Eligible"] = eligible
    out["D5_Selected"] = False
    out["d5_optimized_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    if eligible.any():
        rank = out.loc[eligible].groupby("signal_date")["d5_adjusted_score"].rank(
            method="first", ascending=False
        ).astype("Int64")
        out.loc[eligible, "d5_optimized_rank"] = rank
        selected = eligible & _num(out, "d5_optimized_rank").le(int(p["daily_top_n"]))
        out.loc[selected, "D5_Selected"] = True
    return out


def metrics(frame: pd.DataFrame, *, min_samples: int = 0) -> dict | None:
    if frame.empty:
        return None
    d5 = _num(frame, "D+5")
    valid = d5.notna()
    x = frame.loc[valid].copy()
    d5 = d5.loc[valid]
    if len(d5) < min_samples:
        return None
    excess = _num(x, "D+5_excess") if "D+5_excess" in x.columns else pd.Series(np.nan, index=x.index)
    avg = float(d5.mean())
    med = float(d5.median())
    win = float((d5 > 0).mean())
    avg_excess = float(excess.mean()) if excess.notna().any() else 0.0
    excess_win = float((excess > 0).mean()) if excess.notna().any() else 0.5
    yearly_std = 0.0
    if "signal_date" in x.columns and excess.notna().any():
        years = pd.to_datetime(x["signal_date"], errors="coerce").dt.year
        yearly = excess.groupby(years).mean().dropna()
        if len(yearly) >= 2:
            yearly_std = float(yearly.std(ddof=0))
    objective = (
        0.30 * avg
        + 0.20 * med
        + 0.30 * avg_excess
        + 0.10 * (win - 0.50) * 0.10
        + 0.05 * (excess_win - 0.50) * 0.10
        - 0.05 * yearly_std
    )
    return {
        "sample_count": int(len(d5)),
        "unique_dates": int(pd.to_datetime(x["signal_date"], errors="coerce").nunique()) if "signal_date" in x.columns else 0,
        "avg_D+5": avg,
        "median_D+5": med,
        "win_rate_D+5": win,
        "avg_excess_D+5": avg_excess,
        "excess_win_rate_D+5": excess_win,
        "yearly_excess_std": yearly_std,
        "objective": float(objective),
    }


def _folds(events: pd.DataFrame) -> list[tuple[int, int, int]]:
    years = sorted(pd.to_datetime(events["signal_date"], errors="coerce").dt.year.dropna().astype(int).unique())
    if len(years) < 4:
        raise ValueError("Walk-forward에는 최소 4개 연도가 필요합니다.")
    first = years[0]
    return [(first, test_year - 1, test_year) for test_year in years[3:]]


def _flatten(prefix: str, m: dict | None) -> dict:
    if not m:
        return {}
    return {f"{prefix}_{k}": v for k, v in m.items()}


def _mode(values: list):
    if not values:
        return None
    return pd.Series(values).value_counts().index[0]


def recommend_from_folds(fold_rows: list[dict]) -> dict:
    if not fold_rows:
        return BASELINE.copy()
    rec = {}
    categorical = {"regime", "daily_top_n"}
    for key in BASELINE:
        vals = [row[key] for row in fold_rows if key in row]
        if not vals:
            rec[key] = BASELINE[key]
        elif key in categorical:
            rec[key] = _mode(vals)
        else:
            rec[key] = float(median([float(v) for v in vals]))
    rec["daily_top_n"] = int(rec["daily_top_n"])
    return rec


def main() -> None:
    p = argparse.ArgumentParser(description="KJB D+5 Threshold Optimizer + Walk-forward")
    p.add_argument("--range-dir", default=None)
    p.add_argument("--max-trials", type=int, default=250)
    p.add_argument("--seed", type=int, default=20260908)
    p.add_argument("--min-train-samples", type=int, default=150)
    p.add_argument("--min-test-samples", type=int, default=30)
    args = p.parse_args()

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
    print("KJB D+5 Threshold Optimizer + Walk-forward")
    print("=" * 78)
    print("Range :", range_dir)
    print("Trials:", len(trials))
    print("Folds :", len(folds))

    for fold_no, (train_start, train_end, test_year) in enumerate(folds, start=1):
        train = events[(events["year"] >= train_start) & (events["year"] <= train_end)].copy()
        test = events[events["year"] == test_year].copy()
        best_p = None
        best_m = None

        for trial_no, params in enumerate(trials, start=1):
            selected = apply_trial(train, params)
            train_selected = selected[selected["D5_Selected"]]
            m = metrics(train_selected, min_samples=args.min_train_samples)
            if m is None:
                continue
            row = {"fold": fold_no, "train_start": train_start, "train_end": train_end, "test_year": test_year, "trial": trial_no}
            row.update(params)
            row.update(_flatten("train", m))
            trial_rows.append(row)
            if best_m is None or m["objective"] > best_m["objective"]:
                best_m, best_p = m, params.copy()

        if best_p is None:
            print(f"[WARN] fold {fold_no}: 최소 표본 조건을 만족한 trial 없음")
            continue

        test_scored = apply_trial(test, best_p)
        test_selected = test_scored[test_scored["D5_Selected"]]
        test_m = metrics(test_selected, min_samples=args.min_test_samples)
        row = {"fold": fold_no, "train_start": train_start, "train_end": train_end, "test_year": test_year}
        row.update(best_p)
        row.update(_flatten("train", best_m))
        row.update(_flatten("test", test_m))
        fold_rows.append(row)
        test_text = "n/a" if not test_m else f"D5={test_m['avg_D+5']*100:.2f}% excess={test_m['avg_excess_D+5']*100:.2f}% win={test_m['win_rate_D+5']*100:.1f}%"
        print(f"[Fold {fold_no}] train {train_start}-{train_end} -> test {test_year} | {test_text}")

    if not fold_rows:
        raise RuntimeError("유효한 walk-forward fold가 없습니다. min sample 조건을 낮춰보세요.")

    recommended = recommend_from_folds(fold_rows)
    optimized = apply_trial(events, recommended)
    optimized_selected = optimized[optimized["D5_Selected"]]
    all_m = metrics(optimized_selected, min_samples=1)

    trial_df = pd.DataFrame(trial_rows).sort_values(["fold", "train_objective"], ascending=[True, False]) if trial_rows else pd.DataFrame()
    fold_df = pd.DataFrame(fold_rows)
    summary = pd.DataFrame([{
        **recommended,
        **_flatten("all", all_m),
        "walkforward_folds": len(fold_rows),
        "mean_test_avg_D+5": float(pd.to_numeric(fold_df.get("test_avg_D+5"), errors="coerce").mean()),
        "mean_test_median_D+5": float(pd.to_numeric(fold_df.get("test_median_D+5"), errors="coerce").mean()),
        "mean_test_win_rate_D+5": float(pd.to_numeric(fold_df.get("test_win_rate_D+5"), errors="coerce").mean()),
        "mean_test_avg_excess_D+5": float(pd.to_numeric(fold_df.get("test_avg_excess_D+5"), errors="coerce").mean()),
    }])

    trials_path = range_dir / "kjb_d5_optimizer_trials.csv"
    walk_path = range_dir / "kjb_d5_walkforward.csv"
    best_path = range_dir / "kjb_d5_optimizer_best.json"
    summary_path = range_dir / "kjb_d5_optimizer_summary.csv"
    optimized_path = range_dir / "chart_range_events_d5_optimized.csv"
    if not trial_df.empty:
        trial_df.to_csv(trials_path, index=False, encoding="utf-8-sig")
    fold_df.to_csv(walk_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    optimized.drop(columns=["year"], errors="ignore").to_csv(optimized_path, index=False, encoding="utf-8-sig")
    best_path.write_text(json.dumps({
        "recommended_params": recommended,
        "all_data_metrics_for_reference_only": all_m,
        "note": "Recommended params are aggregated from train-selected fold winners. Walk-forward test columns are the out-of-sample evidence.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[Recommended parameters]")
    print(json.dumps(recommended, ensure_ascii=False, indent=2))
    print("\n[Walk-forward test mean]")
    for col in ["mean_test_avg_D+5", "mean_test_median_D+5", "mean_test_win_rate_D+5", "mean_test_avg_excess_D+5"]:
        v = summary.iloc[0][col]
        print(f"{col:28s}: {v*100:.2f}%" if pd.notna(v) else f"{col:28s}: -")
    print("\n[완료]")
    print("Trials       :", trials_path)
    print("Walk-forward :", walk_path)
    print("Best params  :", best_path)
    print("Summary      :", summary_path)
    print("Optimized evt:", optimized_path)


if __name__ == "__main__":
    main()
