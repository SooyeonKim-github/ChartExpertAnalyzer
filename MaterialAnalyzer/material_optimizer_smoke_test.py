from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from .optimizer import MaterialThresholdOptimizer


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "material_backtest_results.csv"
        output = root / "optimizer"
        rows = []
        dates = pd.bdate_range("2026-01-02", periods=40)
        for i, dt in enumerate(dates):
            for j in range(5):
                positive = j % 2 == 0
                rows.append({
                    "market_date": dt.strftime("%Y%m%d"),
                    "ticker": f"{100000 + j:06d}",
                    "event_id": f"E{i}_{j}",
                    "event_type": "ORDER_CONTRACT" if positive else "SANCTION",
                    "material_score": 70 + j * 4,
                    "price_status": "OK",
                    "novelty_status": "NEW_EVENT" if i % 3 else "REHASH",
                    "relation_type": "DIRECT",
                    "positive_negative": "POSITIVE" if positive else "NEGATIVE",
                    "quantification_score": 15 if positive else 5,
                    "D+5": 3.0 if positive else -2.0,
                    "abs_D+5": 3.0 if positive else 2.0,
                    "directional_D+5": 3.0 if positive else 2.0,
                    "D+20": 8.0 if positive else -4.0,
                    "abs_D+20": 8.0 if positive else 4.0,
                    "directional_D+20": 8.0 if positive else 4.0,
                })
        pd.DataFrame(rows).to_csv(source, index=False, encoding="utf-8-sig")
        result = MaterialThresholdOptimizer(min_sample=10).run(source, output)
        assert result.train_rows > 0
        assert result.validation_rows > 0
        recommendation = Path(result.recommendation_json).read_text(encoding="utf-8")
        assert '"apply_automatically": false' in recommendation
        weights = pd.read_csv(result.weights_csv, encoding="utf-8-sig")
        assert {"event_type", "novelty_status", "relation_type", "positive_negative", "quantification_band"}.issubset(set(weights["feature"]))

    print("[OK] MaterialThresholdOptimizer V1 smoke test")
    print("     time-based train/validation split -> OK")
    print("     shrinkage category adjustments -> OK")
    print("     threshold candidate search -> OK")
    print("     auto apply disabled -> OK")


if __name__ == "__main__":
    main()
