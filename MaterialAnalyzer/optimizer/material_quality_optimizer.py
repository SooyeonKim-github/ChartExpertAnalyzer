from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


BASELINE_THRESHOLDS = {"strong": 85, "confirmed": 70, "watch": 55}

# MaterialAnalyzer is a catalyst-quality classifier, not a return optimizer.
# These catalogs define minimum recognition expectations only. They do not encode
# bullish/bearish direction and they never use forward returns.
HIGH_IMPORTANCE_EVENT_TYPES = {
    "ORDER_CONTRACT", "MNA", "EARNINGS", "GUIDANCE", "PUBLIC_OFFER", "RESTRUCTURING",
    "CAPEX", "INVESTMENT", "ASSET_TRANSACTION", "CAPITAL_RAISE", "BUYBACK", "VALUE_UP",
    "CAPITAL_REDUCTION", "APPROVAL", "CLINICAL", "TRADING_HALT", "SANCTION", "RECALL",
}

CORE_MATERIAL_EVENT_TYPES = HIGH_IMPORTANCE_EVENT_TYPES | {
    "DIVIDEND", "TREASURY_STOCK_DISPOSAL", "CONVERTIBLE_EXERCISE", "INVESTMENT_DISPOSAL",
    "DERIVATIVE_LOSS", "PRICE_INCREASE", "SHORTAGE", "GOV_POLICY", "LITIGATION", "SUBSIDY",
    "DEFENSE", "NUCLEAR", "AI_DATACENTER", "PRODUCT", "CONVERTIBLE_ADJUSTMENT", "FINANCING",
    "MATERIAL_MANAGEMENT", "AI", "SEMICONDUCTOR", "SECONDARY_BATTERY", "SHIPBUILDING", "BIO",
    "DEBT_GUARANTEE", "SHARE_CONSOLIDATION", "PARTNERSHIP", "SUPPLY", "REGULATION", "PATENT",
    "OWNERSHIP_CHANGE", "TRADING_RESUME",
}

ROUTINE_EVENT_TYPES = {
    "ROUTINE_DISCLOSURE", "IR_EVENT", "SECURITIES_FILING", "INSIDER_OWNERSHIP",
    "ETF_ADMIN", "SHORT_SELL_RESTRICTION",
}

QUALITY_GUARDRAILS = {
    "unknown_rate": {"direction": "MAX", "target": 0.20, "weight": 20.0},
    "core_below_watch_rate": {"direction": "MAX", "target": 0.10, "weight": 20.0},
    "high_below_confirmed_rate": {"direction": "MAX", "target": 0.25, "weight": 15.0},
    "direct_link_coverage": {"direction": "MIN", "target": 0.95, "weight": 15.0},
    "unresolved_rate": {"direction": "MAX", "target": 0.05, "weight": 10.0},
    "routine_promoted_rate": {"direction": "MAX", "target": 0.02, "weight": 10.0},
    "source_coverage_ok_rate": {"direction": "MIN", "target": 0.90, "weight": 10.0},
}


@dataclass
class QualityOptimizerRunResult:
    event_rows: int
    score_rows: int
    linked_rows: int
    quality_score: float
    decision: str
    metrics_csv: Path
    event_types_csv: Path
    threshold_candidates_csv: Path
    threshold_comparison_csv: Path
    recommendation_json: Path


def _read_csv(path: Path, *, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"required quality input not found: {path}")
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _nonempty(series: pd.Series) -> pd.Series:
    text = _text(series).str.lower()
    return ~text.isin({"", "nan", "none", "null", "[]"})


def _status_rank(status: str) -> int:
    return {"REJECT": 0, "WATCH": 1, "CONFIRMED": 2, "STRONG": 3}.get(str(status).upper(), 0)


def _status_from_score(score: pd.Series, thresholds: dict[str, int]) -> pd.Series:
    values = _num(score)
    result = pd.Series("REJECT", index=score.index, dtype=object)
    result.loc[values >= thresholds["watch"]] = "WATCH"
    result.loc[values >= thresholds["confirmed"]] = "CONFIRMED"
    result.loc[values >= thresholds["strong"]] = "STRONG"
    return result


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _guardrail_score(value: float, direction: str, target: float) -> float:
    value = max(0.0, float(value))
    target = max(1e-9, float(target))
    if direction == "MIN":
        return 100.0 if value >= target else max(0.0, min(100.0, 100.0 * value / target))
    if value <= target:
        return 100.0
    # Gracefully decay to zero at 2x target rather than hard-failing one noisy metric.
    return max(0.0, min(100.0, 100.0 * (1.0 - (value - target) / target)))


class MaterialQualityOptimizer:
    """Audit and calibrate catalyst-quality classification without using forward returns.

    Inputs are historical derived reports. Market-reaction/backtest files are intentionally
    not read. The optimizer only proposes threshold candidates and quality findings; it never
    writes back to MaterialScorer automatically.
    """

    VERSION = "MATERIAL_QUALITY_OPTIMIZER_V1"

    def __init__(self, history_dir: str | Path):
        self.history_dir = Path(history_dir)

    def _load(self):
        events = _read_csv(self.history_dir / "event_report.csv")
        scores = _read_csv(self.history_dir / "material_score_report.csv")
        links = _read_csv(self.history_dir / "ticker_link_report.csv")
        unresolved = _read_csv(self.history_dir / "ticker_link_unresolved.csv", required=False)
        coverage = _read_csv(self.history_dir / "historical_source_coverage.csv", required=False)

        for frame, required, label in (
            (events, {"event_id", "event_type", "material_candidate", "stock_codes"}, "event_report"),
            (scores, {"event_id", "event_type", "material_score", "material_status"}, "material_score_report"),
            (links, {"event_id", "relation_type", "ticker"}, "ticker_link_report"),
        ):
            missing = sorted(required - set(frame.columns))
            if missing:
                raise ValueError(f"{label} columns missing: {missing}")

        events["event_type"] = _text(events["event_type"]).str.upper()
        events["material_candidate"] = _num(events["material_candidate"]).fillna(0).astype(int)
        scores["event_type"] = _text(scores["event_type"]).str.upper()
        scores["material_score"] = _num(scores["material_score"])
        scores["material_status"] = _text(scores["material_status"]).str.upper()
        links["relation_type"] = _text(links["relation_type"]).str.upper()
        return events, scores, links, unresolved, coverage

    @staticmethod
    def _threshold_quality(scores: pd.DataFrame, thresholds: dict[str, int]) -> dict:
        status = _status_from_score(scores["material_score"], thresholds)
        event_type = scores["event_type"]
        core = event_type.isin(CORE_MATERIAL_EVENT_TYPES)
        high = event_type.isin(HIGH_IMPORTANCE_EVENT_TYPES)
        routine = event_type.isin(ROUTINE_EVENT_TYPES)

        core_count = int(core.sum())
        high_count = int(high.sum())
        routine_count = int(routine.sum())
        core_recall = _ratio(int((core & (status.map(_status_rank) >= 1)).sum()), core_count)
        high_confirmed_recall = _ratio(int((high & (status.map(_status_rank) >= 2)).sum()), high_count)
        routine_rejection = 1.0 if routine_count == 0 else _ratio(int((routine & (status == "REJECT")).sum()), routine_count)

        # Quality objective rewards recognition of important catalysts and rejection of
        # administrative noise. It contains no D+N return or market-reaction term.
        objective = 0.45 * high_confirmed_recall + 0.40 * core_recall + 0.15 * routine_rejection
        return {
            "objective": objective,
            "core_count": core_count,
            "core_watch_recall": core_recall,
            "high_count": high_count,
            "high_confirmed_recall": high_confirmed_recall,
            "routine_count": routine_count,
            "routine_rejection_rate": routine_rejection,
            "strong_count": int((status == "STRONG").sum()),
            "confirmed_count": int((status == "CONFIRMED").sum()),
            "watch_count": int((status == "WATCH").sum()),
            "reject_count": int((status == "REJECT").sum()),
        }

    def _threshold_candidates(self, scores: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for strong in range(80, 96, 5):
            for confirmed in range(65, strong, 5):
                for watch in range(50, confirmed, 5):
                    thresholds = {"strong": strong, "confirmed": confirmed, "watch": watch}
                    q = self._threshold_quality(scores, thresholds)
                    rows.append({
                        "strong_threshold": strong,
                        "confirmed_threshold": confirmed,
                        "watch_threshold": watch,
                        "quality_objective": round(q["objective"], 8),
                        **{k: v for k, v in q.items() if k != "objective"},
                    })
        out = pd.DataFrame(rows)
        return out.sort_values(
            ["quality_objective", "high_confirmed_recall", "core_watch_recall", "strong_threshold"],
            ascending=[False, False, False, False],
            kind="stable",
        ).reset_index(drop=True)

    def _event_type_audit(self, events: pd.DataFrame, scores: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
        score_cols = ["event_id", "material_score", "material_status"]
        joined = events.merge(scores[score_cols], on="event_id", how="left")
        direct_linked = set(links.loc[links["relation_type"] == "DIRECT", "event_id"].astype(str))
        rows = []
        for event_type, group in joined.groupby("event_type", dropna=False, sort=True):
            scores_num = _num(group["material_score"])
            status = _text(group["material_status"]).str.upper()
            direct_company = _nonempty(group["stock_codes"])
            direct_link_count = int(group.loc[direct_company, "event_id"].astype(str).isin(direct_linked).sum())
            rows.append({
                "event_type": event_type or "UNKNOWN",
                "event_count": int(len(group)),
                "material_candidate_count": int((_num(group["material_candidate"]).fillna(0) > 0).sum()),
                "material_candidate_rate": round(float((_num(group["material_candidate"]).fillna(0) > 0).mean()), 6),
                "scored_count": int(scores_num.notna().sum()),
                "avg_material_score": round(float(scores_num.mean()), 4) if scores_num.notna().any() else pd.NA,
                "strong_count": int((status == "STRONG").sum()),
                "confirmed_count": int((status == "CONFIRMED").sum()),
                "watch_count": int((status == "WATCH").sum()),
                "reject_count": int((status == "REJECT").sum()),
                "direct_company_count": int(direct_company.sum()),
                "direct_linked_count": direct_link_count,
                "direct_link_coverage": round(_ratio(direct_link_count, int(direct_company.sum())), 6) if direct_company.any() else pd.NA,
                "quality_class": (
                    "HIGH_IMPORTANCE" if event_type in HIGH_IMPORTANCE_EVENT_TYPES else
                    "CORE_MATERIAL" if event_type in CORE_MATERIAL_EVENT_TYPES else
                    "ROUTINE" if event_type in ROUTINE_EVENT_TYPES else "OTHER"
                ),
            })
        return pd.DataFrame(rows)

    def _metrics(self, events: pd.DataFrame, scores: pd.DataFrame, links: pd.DataFrame, unresolved: pd.DataFrame, coverage: pd.DataFrame):
        event_type = events["event_type"]
        unknown_count = int((event_type == "UNKNOWN").sum())
        unknown_rate = _ratio(unknown_count, len(events))

        core = scores["event_type"].isin(CORE_MATERIAL_EVENT_TYPES)
        high = scores["event_type"].isin(HIGH_IMPORTANCE_EVENT_TYPES)
        score_status_rank = scores["material_status"].map(_status_rank)
        core_below_watch = int((core & (score_status_rank < 1)).sum())
        high_below_confirmed = int((high & (score_status_rank < 2)).sum())
        core_below_watch_rate = _ratio(core_below_watch, int(core.sum()))
        high_below_confirmed_rate = _ratio(high_below_confirmed, int(high.sum()))

        direct_candidates = events.loc[
            (events["material_candidate"] > 0) & _nonempty(events["stock_codes"]), "event_id"
        ].astype(str)
        direct_candidate_set = set(direct_candidates)
        direct_linked_set = set(links.loc[links["relation_type"] == "DIRECT", "event_id"].astype(str))
        direct_link_coverage = _ratio(len(direct_candidate_set & direct_linked_set), len(direct_candidate_set))

        unresolved_count = int(unresolved["event_id"].astype(str).nunique()) if (not unresolved.empty and "event_id" in unresolved.columns) else 0
        scored_unique = int(scores["event_id"].astype(str).nunique())
        unresolved_rate = _ratio(unresolved_count, scored_unique)

        routine_mask = scores["event_type"].isin(ROUTINE_EVENT_TYPES)
        routine_count = int(routine_mask.sum())
        routine_promoted = int((routine_mask & (score_status_rank >= 2)).sum())
        routine_promoted_rate = _ratio(routine_promoted, routine_count) if routine_count else 0.0

        if not coverage.empty and "status" in coverage.columns:
            status = _text(coverage["status"]).str.upper()
            source_coverage_ok_rate = float(status.isin({"OK", "COMPLETE"}).mean()) if len(status) else 0.0
        else:
            source_coverage_ok_rate = 0.0

        raw_metrics = {
            "unknown_rate": unknown_rate,
            "core_below_watch_rate": core_below_watch_rate,
            "high_below_confirmed_rate": high_below_confirmed_rate,
            "direct_link_coverage": direct_link_coverage,
            "unresolved_rate": unresolved_rate,
            "routine_promoted_rate": routine_promoted_rate,
            "source_coverage_ok_rate": source_coverage_ok_rate,
        }

        rows = []
        weighted = 0.0
        total_weight = 0.0
        for metric, cfg in QUALITY_GUARDRAILS.items():
            value = raw_metrics[metric]
            component = _guardrail_score(value, cfg["direction"], cfg["target"])
            passed = value <= cfg["target"] if cfg["direction"] == "MAX" else value >= cfg["target"]
            weighted += component * cfg["weight"]
            total_weight += cfg["weight"]
            rows.append({
                "metric": metric,
                "value": round(value, 6),
                "direction": cfg["direction"],
                "target": cfg["target"],
                "status": "PASS" if passed else "WARN",
                "component_score": round(component, 2),
                "weight": cfg["weight"],
            })
        quality_score = weighted / total_weight if total_weight else 0.0
        return pd.DataFrame(rows), round(quality_score, 2)

    def run(self, output_dir: str | Path) -> QualityOptimizerRunResult:
        events, scores, links, unresolved, coverage = self._load()
        metrics, quality_score = self._metrics(events, scores, links, unresolved, coverage)
        event_types = self._event_type_audit(events, scores, links)
        candidates = self._threshold_candidates(scores)
        best = candidates.iloc[0]
        candidate_thresholds = {
            "strong": int(best["strong_threshold"]),
            "confirmed": int(best["confirmed_threshold"]),
            "watch": int(best["watch_threshold"]),
        }

        comparison_rows = []
        for name, thresholds in (("BASELINE", BASELINE_THRESHOLDS), ("QUALITY_CANDIDATE", candidate_thresholds)):
            q = self._threshold_quality(scores, thresholds)
            comparison_rows.append({
                "config": name,
                **thresholds,
                "quality_objective": round(q.pop("objective"), 8),
                **q,
            })
        comparison = pd.DataFrame(comparison_rows)

        decision = "PASS" if quality_score >= 80 else "REVIEW_REQUIRED" if quality_score >= 65 else "QUALITY_BLOCKED"
        failed_guardrails = metrics.loc[metrics["status"] != "PASS", "metric"].tolist()

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        metrics_csv = output / "material_quality_metrics.csv"
        event_types_csv = output / "material_quality_event_types.csv"
        threshold_candidates_csv = output / "material_quality_threshold_candidates.csv"
        threshold_comparison_csv = output / "material_quality_threshold_comparison.csv"
        recommendation_json = output / "material_quality_recommendation.json"

        metrics.to_csv(metrics_csv, index=False, encoding="utf-8-sig")
        event_types.to_csv(event_types_csv, index=False, encoding="utf-8-sig")
        candidates.head(100).to_csv(threshold_candidates_csv, index=False, encoding="utf-8-sig")
        comparison.to_csv(threshold_comparison_csv, index=False, encoding="utf-8-sig")

        recommendation = {
            "optimizer_version": self.VERSION,
            "purpose": "material_quality_not_return_maximization",
            "uses_forward_returns": False,
            "apply_automatically": False,
            "decision": decision,
            "quality_score": quality_score,
            "failed_guardrails": failed_guardrails,
            "baseline_thresholds": BASELINE_THRESHOLDS,
            "quality_candidate_thresholds": candidate_thresholds,
            "notes": [
                "Material score measures catalyst importance/certainty, not expected stock return.",
                "Positive/negative direction is audited separately and does not reduce importance.",
                "Forward-return backtests remain a separate post-hoc market-reaction diagnostic.",
                "Threshold candidates are taxonomy-quality suggestions only and are never auto-applied.",
            ],
        }
        recommendation_json.write_text(json.dumps(recommendation, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=" * 80)
        print("MaterialQualityOptimizer V1 - catalyst quality / no return objective")
        print("=" * 80)
        print(f"history dir     : {self.history_dir}")
        print(f"events          : {len(events):,}")
        print(f"scores          : {len(scores):,}")
        print(f"links           : {len(links):,}")
        print(f"quality score   : {quality_score:.2f}/100")
        print(f"decision        : {decision}")
        print(f"failed guards   : {', '.join(failed_guardrails) if failed_guardrails else 'NONE'}")
        print(f"baseline        : {BASELINE_THRESHOLDS}")
        print(f"candidate       : {candidate_thresholds}")
        print("FORWARD RETURNS : NOT USED")
        print("AUTO APPLY      : DISABLED")
        print(f"metrics         : {metrics_csv}")
        print(f"event types     : {event_types_csv}")
        print(f"thresholds      : {threshold_candidates_csv}")
        print(f"comparison      : {threshold_comparison_csv}")
        print(f"recommendation  : {recommendation_json}")
        print("=" * 80)

        return QualityOptimizerRunResult(
            event_rows=len(events),
            score_rows=len(scores),
            linked_rows=len(links),
            quality_score=quality_score,
            decision=decision,
            metrics_csv=metrics_csv,
            event_types_csv=event_types_csv,
            threshold_candidates_csv=threshold_candidates_csv,
            threshold_comparison_csv=threshold_comparison_csv,
            recommendation_json=recommendation_json,
        )
