from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

from .optimizer import MaterialQualityOptimizer


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        history = root / "history"
        output = root / "quality_optimizer"
        history.mkdir(parents=True, exist_ok=True)

        events = pd.DataFrame([
            {"event_id": "E1", "event_type": "ORDER_CONTRACT", "material_candidate": 1, "stock_codes": "005930", "material_candidate_reason": "MATERIAL_EVENT"},
            {"event_id": "E2", "event_type": "MNA", "material_candidate": 1, "stock_codes": "000660", "material_candidate_reason": "MATERIAL_EVENT"},
            {"event_id": "E3", "event_type": "VALUE_UP", "material_candidate": 1, "stock_codes": "035420", "material_candidate_reason": "MATERIAL_EVENT"},
            {"event_id": "E4", "event_type": "ROUTINE_DISCLOSURE", "material_candidate": 0, "stock_codes": "005930", "material_candidate_reason": "ADMINISTRATIVE_ROUTINE_DISCLOSURE"},
            {"event_id": "E5", "event_type": "UNKNOWN", "material_candidate": 0, "stock_codes": "", "material_candidate_reason": "UNKNOWN_EVENT"},
        ])
        scores = pd.DataFrame([
            {"event_id": "E1", "event_type": "ORDER_CONTRACT", "material_score": 90, "material_status": "STRONG"},
            {"event_id": "E2", "event_type": "MNA", "material_score": 82, "material_status": "CONFIRMED"},
            {"event_id": "E3", "event_type": "VALUE_UP", "material_score": 72, "material_status": "CONFIRMED"},
        ])
        links = pd.DataFrame([
            {"event_id": "E1", "relation_type": "DIRECT", "ticker": "005930"},
            {"event_id": "E2", "relation_type": "DIRECT", "ticker": "000660"},
            {"event_id": "E3", "relation_type": "DIRECT", "ticker": "035420"},
        ])
        unresolved = pd.DataFrame(columns=["event_id", "unresolved_reason"])
        coverage = pd.DataFrame([
            {"source_id": "DART", "date": "2026-01-02", "status": "OK"},
            {"source_id": "DART", "date": "2026-01-03", "status": "OK"},
        ])

        events.to_csv(history / "event_report.csv", index=False, encoding="utf-8-sig")
        scores.to_csv(history / "material_score_report.csv", index=False, encoding="utf-8-sig")
        links.to_csv(history / "ticker_link_report.csv", index=False, encoding="utf-8-sig")
        unresolved.to_csv(history / "ticker_link_unresolved.csv", index=False, encoding="utf-8-sig")
        coverage.to_csv(history / "historical_source_coverage.csv", index=False, encoding="utf-8-sig")

        result = MaterialQualityOptimizer(history).run(output)
        assert result.event_rows == 5
        assert result.score_rows == 3
        assert result.quality_score > 0
        metrics = pd.read_csv(result.metrics_csv, encoding="utf-8-sig")
        assert "unknown_rate" in set(metrics["metric"])
        assert "direct_link_coverage" in set(metrics["metric"])
        comparison = pd.read_csv(result.threshold_comparison_csv, encoding="utf-8-sig")
        assert {"BASELINE", "QUALITY_CANDIDATE"}.issubset(set(comparison["config"]))
        recommendation = json.loads(Path(result.recommendation_json).read_text(encoding="utf-8"))
        assert recommendation["uses_forward_returns"] is False
        assert recommendation["apply_automatically"] is False

    print("[OK] MaterialQualityOptimizer V1 smoke test")
    print("     catalyst-quality metrics -> OK")
    print("     direct-link / UNKNOWN / coverage guardrails -> OK")
    print("     taxonomy threshold candidate search -> OK")
    print("     forward-return objective disabled -> OK")
    print("     auto apply disabled -> OK")


if __name__ == "__main__":
    main()
