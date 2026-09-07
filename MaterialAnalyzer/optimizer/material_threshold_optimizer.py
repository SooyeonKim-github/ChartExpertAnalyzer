from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


BASELINE_THRESHOLDS = {"strong": 85, "confirmed": 70, "watch": 55}
DEFAULT_MIN_SAMPLE = 100


@dataclass
class OptimizerRunResult:
    input_rows: int
    train_rows: int
    validation_rows: int
    scored_csv: Path
    weights_csv: Path
    candidates_csv: Path
    validation_csv: Path
    recommendation_json: Path


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return float("nan")
    v = values.loc[mask].astype(float)
    w = weights.loc[mask].astype(float)
    return float(np.average(v, weights=w))


def _safe_num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _reaction_target(frame: pd.DataFrame) -> pd.Series:
    """Composite market-reaction target in roughly [-1, 1]."""
    d5 = _safe_num(frame, "directional_D+5")
    d20 = _safe_num(frame, "directional_D+20")
    a5 = _safe_num(frame, "abs_D+5")
    a20 = _safe_num(frame, "abs_D+20")
    parts = []
    weights = []
    for series, scale, weight in (
        (d5, 5.0, 0.35),
        (d20, 10.0, 0.35),
        (a5, 5.0, 0.15),
        (a20, 10.0, 0.15),
    ):
        parts.append(np.tanh(series / scale) * weight)
        weights.append(series.notna().astype(float) * weight)
    numerator = sum(part.fillna(0.0) for part in parts)
    denominator = sum(weights)
    return numerator / denominator.replace(0, np.nan)


def _quant_band(value) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if x <= 0:
        return "0"
    if x <= 5:
        return "1-5"
    if x <= 10:
        return "6-10"
    return "11-15"


def _status_from_thresholds(score: pd.Series, thresholds: dict[str, int]) -> pd.Series:
    strong, confirmed, watch = thresholds["strong"], thresholds["confirmed"], thresholds["watch"]
    return pd.Series(
        np.select(
            [score >= strong, score >= confirmed, score >= watch],
            ["STRONG", "CONFIRMED", "WATCH"],
            default="REJECT",
        ),
        index=score.index,
    )


class MaterialThresholdOptimizer:
    """Shrinkage-based candidate optimizer. Never auto-applies production rules."""

    VERSION = "MATERIAL_THRESHOLD_OPTIMIZER_V1"
    FEATURE_SPECS = (
        ("event_type", "event_type", 10.0),
        ("novelty_status", "novelty_status", 4.0),
        ("relation_type", "relation_type", 4.0),
        ("positive_negative", "positive_negative", 4.0),
        ("quantification_band", "_quantification_band", 4.0),
    )

    def __init__(self, min_sample: int = DEFAULT_MIN_SAMPLE):
        self.min_sample = max(10, int(min_sample))

    @staticmethod
    def _load(path: str | Path) -> pd.DataFrame:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"backtest results not found: {source}")
        frame = pd.read_csv(source, encoding="utf-8-sig", dtype={"ticker": str, "market_date": str})
        required = {"ticker", "market_date", "material_score", "event_type", "price_status"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"optimizer input columns missing: {missing}")
        frame["ticker"] = frame["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
        frame["market_date"] = frame["market_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        frame = frame.loc[frame["price_status"].astype(str) == "OK"].copy()
        frame["material_score"] = pd.to_numeric(frame["material_score"], errors="coerce")
        frame = frame.dropna(subset=["material_score"])
        frame["_target"] = _reaction_target(frame)
        frame = frame.dropna(subset=["_target"])
        dup = frame.groupby(["ticker", "market_date"])["ticker"].transform("size").clip(lower=1)
        frame["_sample_weight"] = 1.0 / dup.astype(float)
        if "quantification_score" in frame.columns:
            quant = pd.to_numeric(frame["quantification_score"], errors="coerce").fillna(0.0)
        else:
            quant = pd.Series(0.0, index=frame.index)
        frame["_quantification_band"] = quant.map(_quant_band)
        for column in ("novelty_status", "relation_type", "positive_negative"):
            if column not in frame.columns:
                frame[column] = ""
        return frame.sort_values(["market_date", "ticker"], kind="stable").reset_index(drop=True)

    @staticmethod
    def _split(frame: pd.DataFrame, train_end: str | None = None, validation_start: str | None = None):
        dates = frame["market_date"].astype(str)
        unique_dates = sorted(d for d in dates.unique() if len(d) == 8)
        if len(unique_dates) < 2:
            raise ValueError("optimizer needs at least two market dates")
        if train_end:
            train = frame.loc[dates <= train_end].copy()
            if validation_start:
                start = validation_start
            else:
                later = [d for d in unique_dates if d > train_end]
                if not later:
                    raise ValueError(f"no validation date after train_end={train_end}")
                start = later[0]
            validation = frame.loc[dates >= start].copy()
            meta = {"mode": "EXPLICIT", "train_end": train_end, "validation_start": start}
        else:
            cut_index = min(max(int(len(unique_dates) * 0.8), 1), len(unique_dates) - 1)
            validation_first = unique_dates[cut_index]
            train_last = unique_dates[cut_index - 1]
            train = frame.loc[dates <= train_last].copy()
            validation = frame.loc[dates >= validation_first].copy()
            meta = {"mode": "TIME_80_20", "train_end": train_last, "validation_start": validation_first}
        if train.empty or validation.empty:
            raise ValueError(f"empty train/validation split: train={len(train)} validation={len(validation)} meta={meta}")
        return train, validation, meta

    def _fit_adjustments(self, train: pd.DataFrame):
        overall = _weighted_mean(train["_target"], train["_sample_weight"])
        target_std = float(train["_target"].std(ddof=0))
        target_std = target_std if np.isfinite(target_std) and target_std > 1e-6 else 0.25
        records = []
        lookup = {}
        for feature_name, column, max_adjustment in self.FEATURE_SPECS:
            values = train[column].fillna("").astype(str)
            for value in sorted(v for v in values.unique() if v):
                group = train.loc[values == value]
                effective_n = float(group["_sample_weight"].sum())
                raw_mean = _weighted_mean(group["_target"], group["_sample_weight"])
                raw_effect = 0.0 if not np.isfinite(raw_mean) else raw_mean - overall
                reliability = effective_n / (effective_n + self.min_sample)
                standardized = raw_effect / target_std
                adjustment = float(np.clip(standardized * max_adjustment * reliability, -max_adjustment, max_adjustment))
                if effective_n < self.min_sample * 0.25:
                    adjustment = 0.0
                adjustment = round(adjustment, 4)
                lookup[(feature_name, value)] = adjustment
                records.append({
                    "feature": feature_name,
                    "value": value,
                    "row_count": int(len(group)),
                    "effective_sample": round(effective_n, 4),
                    "target_mean": round(raw_mean, 6) if np.isfinite(raw_mean) else np.nan,
                    "overall_target_mean": round(overall, 6),
                    "raw_effect": round(raw_effect, 6),
                    "reliability": round(reliability, 6),
                    "score_adjustment": adjustment,
                    "max_abs_adjustment": max_adjustment,
                    "min_sample": self.min_sample,
                })
        return pd.DataFrame(records), lookup

    def _apply_adjustments(self, frame: pd.DataFrame, lookup):
        out = frame.copy()
        total = pd.Series(0.0, index=out.index)
        for feature_name, column, _ in self.FEATURE_SPECS:
            adj_col = f"adj_{feature_name}"
            out[adj_col] = [lookup.get((feature_name, str(value or "")), 0.0) for value in out[column].fillna("").astype(str)]
            total = total + pd.to_numeric(out[adj_col], errors="coerce").fillna(0.0)
        out["optimizer_adjustment"] = total.round(4)
        out["optimized_material_score"] = (pd.to_numeric(out["material_score"], errors="coerce").fillna(0.0) + total).clip(0, 100).round(4)
        return out

    def _threshold_metric(self, frame: pd.DataFrame, score_column: str, thresholds: dict[str, int]):
        status = _status_from_thresholds(pd.to_numeric(frame[score_column], errors="coerce"), thresholds)
        stats = {}
        for tier in ("STRONG", "CONFIRMED", "WATCH", "REJECT"):
            group = frame.loc[status == tier]
            eff_n = float(group["_sample_weight"].sum())
            mean = _weighted_mean(group["_target"], group["_sample_weight"]) if len(group) else float("nan")
            stats[tier] = {"count": int(len(group)), "effective_n": eff_n, "target_mean": mean}
        tier_weights = {"STRONG": 0.50, "CONFIRMED": 0.30, "WATCH": 0.20}
        objective = 0.0
        valid_weight = 0.0
        for tier, weight in tier_weights.items():
            metric = stats[tier]
            if metric["effective_n"] >= self.min_sample and np.isfinite(metric["target_mean"]):
                objective += weight * metric["target_mean"]
                valid_weight += weight
        objective = objective / valid_weight if valid_weight else -999.0
        means = [stats[t]["target_mean"] for t in ("STRONG", "CONFIRMED", "WATCH")]
        if all(np.isfinite(x) for x in means):
            objective += 0.15 * (means[0] - means[2])
            if means[0] < means[1]:
                objective -= 0.20 * (means[1] - means[0])
            if means[1] < means[2]:
                objective -= 0.10 * (means[2] - means[1])
        if stats["STRONG"]["effective_n"] < self.min_sample:
            objective -= 0.25
        if stats["CONFIRMED"]["effective_n"] < self.min_sample:
            objective -= 0.15
        return {"objective": float(objective), "stats": stats}

    def _search_thresholds(self, train: pd.DataFrame) -> pd.DataFrame:
        records = []
        for strong in range(75, 96, 5):
            for confirmed in range(60, strong, 5):
                for watch in range(45, confirmed, 5):
                    thresholds = {"strong": strong, "confirmed": confirmed, "watch": watch}
                    metric = self._threshold_metric(train, "optimized_material_score", thresholds)
                    stats = metric["stats"]
                    records.append({
                        "strong_threshold": strong,
                        "confirmed_threshold": confirmed,
                        "watch_threshold": watch,
                        "train_objective": round(metric["objective"], 8),
                        "strong_count": stats["STRONG"]["count"],
                        "strong_effective_n": round(stats["STRONG"]["effective_n"], 4),
                        "strong_target_mean": stats["STRONG"]["target_mean"],
                        "confirmed_count": stats["CONFIRMED"]["count"],
                        "confirmed_effective_n": round(stats["CONFIRMED"]["effective_n"], 4),
                        "confirmed_target_mean": stats["CONFIRMED"]["target_mean"],
                        "watch_count": stats["WATCH"]["count"],
                        "watch_effective_n": round(stats["WATCH"]["effective_n"], 4),
                        "watch_target_mean": stats["WATCH"]["target_mean"],
                    })
        return pd.DataFrame(records).sort_values(["train_objective", "strong_effective_n"], ascending=[False, False], kind="stable").reset_index(drop=True)

    def _validation_rows(self, validation: pd.DataFrame, candidate: dict[str, int]) -> pd.DataFrame:
        rows = []
        for config_name, score_column, thresholds in (
            ("BASELINE", "material_score", BASELINE_THRESHOLDS),
            ("OPTIMIZED_CANDIDATE", "optimized_material_score", candidate),
        ):
            metric = self._threshold_metric(validation, score_column, thresholds)
            for tier, stats in metric["stats"].items():
                rows.append({
                    "config": config_name,
                    "tier": tier,
                    "score_column": score_column,
                    "strong_threshold": thresholds["strong"],
                    "confirmed_threshold": thresholds["confirmed"],
                    "watch_threshold": thresholds["watch"],
                    "validation_objective": round(metric["objective"], 8),
                    "count": stats["count"],
                    "effective_sample": round(stats["effective_n"], 4),
                    "target_mean": round(stats["target_mean"], 6) if np.isfinite(stats["target_mean"]) else np.nan,
                })
        return pd.DataFrame(rows)

    def run(self, input_path: str | Path, output_dir: str | Path, *, train_end: str | None = None, validation_start: str | None = None) -> OptimizerRunResult:
        frame = self._load(input_path)
        train, validation, split_meta = self._split(frame, train_end, validation_start)
        weights, lookup = self._fit_adjustments(train)
        train_scored = self._apply_adjustments(train, lookup)
        validation_scored = self._apply_adjustments(validation, lookup)
        candidates = self._search_thresholds(train_scored)
        if candidates.empty:
            raise RuntimeError("threshold search produced no candidates")
        best = candidates.iloc[0]
        candidate_thresholds = {
            "strong": int(best["strong_threshold"]),
            "confirmed": int(best["confirmed_threshold"]),
            "watch": int(best["watch_threshold"]),
        }
        validation_report = self._validation_rows(validation_scored, candidate_thresholds)
        scored = pd.concat([
            train_scored.assign(optimizer_split="TRAIN"),
            validation_scored.assign(optimizer_split="VALIDATION"),
        ], ignore_index=True).sort_values(["market_date", "ticker"], kind="stable")
        baseline_obj = float(validation_report.loc[validation_report["config"] == "BASELINE", "validation_objective"].iloc[0])
        candidate_obj = float(validation_report.loc[validation_report["config"] == "OPTIMIZED_CANDIDATE", "validation_objective"].iloc[0])

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        scored_csv = output / "material_optimizer_scored.csv"
        weights_csv = output / "material_optimizer_weights.csv"
        candidates_csv = output / "material_optimizer_candidates.csv"
        validation_csv = output / "material_optimizer_validation.csv"
        recommendation_json = output / "material_optimizer_recommendation.json"
        scored.to_csv(scored_csv, index=False, encoding="utf-8-sig")
        weights.to_csv(weights_csv, index=False, encoding="utf-8-sig")
        candidates.head(100).to_csv(candidates_csv, index=False, encoding="utf-8-sig")
        validation_report.to_csv(validation_csv, index=False, encoding="utf-8-sig")

        recommendation = {
            "optimizer_version": self.VERSION,
            "apply_automatically": False,
            "decision": "REVIEW_REQUIRED",
            "input_rows": int(len(frame)),
            "train_rows": int(len(train)),
            "validation_rows": int(len(validation)),
            "split": split_meta,
            "min_sample": self.min_sample,
            "baseline_thresholds": BASELINE_THRESHOLDS,
            "candidate_thresholds": candidate_thresholds,
            "validation_baseline_objective": baseline_obj,
            "validation_candidate_objective": candidate_obj,
            "validation_improvement": round(candidate_obj - baseline_obj, 8),
            "notes": [
                "Candidate weights/thresholds are not written back to MaterialScorer.",
                "Ticker-day duplicate filings are de-biased through inverse duplicate sample weights.",
                "Category effects use shrinkage and minimum-sample guards.",
                "Re-run on a longer history and an out-of-sample validation window before production use.",
            ],
        }
        recommendation_json.write_text(json.dumps(recommendation, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=" * 80)
        print("MaterialThresholdOptimizer V1 - candidate only / no auto apply")
        print("=" * 80)
        print(f"input rows       : {len(frame):,}")
        print(f"train rows       : {len(train):,} <= {split_meta['train_end']}")
        print(f"validation rows  : {len(validation):,} >= {split_meta['validation_start']}")
        print(f"min sample       : {self.min_sample}")
        print(f"baseline         : {BASELINE_THRESHOLDS}")
        print(f"candidate        : {candidate_thresholds}")
        print(f"validation delta : {candidate_obj - baseline_obj:+.6f}")
        print("AUTO APPLY       : DISABLED")
        print(f"weights          : {weights_csv}")
        print(f"candidates       : {candidates_csv}")
        print(f"validation       : {validation_csv}")
        print(f"recommendation   : {recommendation_json}")
        print("=" * 80)
        return OptimizerRunResult(
            input_rows=len(frame), train_rows=len(train), validation_rows=len(validation),
            scored_csv=scored_csv, weights_csv=weights_csv, candidates_csv=candidates_csv,
            validation_csv=validation_csv, recommendation_json=recommendation_json,
        )
