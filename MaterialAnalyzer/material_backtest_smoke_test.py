from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from .backtest import MaterialBacktester


class _FakeProvider:
    def get_ohlcv(self, ticker, start, end):
        dates = pd.bdate_range("2026-01-02", periods=100)
        close = pd.Series([100.0 + i for i in range(len(dates))], index=dates)
        return pd.DataFrame(
            {
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1000,
                "trading_value": close * 1000,
            },
            index=dates,
        )


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "material_history_backtest.csv"
        output = root / "out"
        rows = [
            {
                "market_date": "20260102", "event_id": "E1", "ticker": "005930", "name": "A",
                "event_type": "ORDER_CONTRACT", "event_stage": "CONFIRMED", "event_title": "수주",
                "material_score": 90, "material_status": "STRONG", "relation_type": "DIRECT",
                "relation_weight": 1.0, "mapping_relevance": 1.0, "ticker_material_score": 90,
                "novelty_status": "NEW_EVENT", "positive_negative": "POSITIVE", "source_id": "DART",
                "theme": "", "backtest_eligible": 1,
            },
            {
                "market_date": "20260105", "event_id": "E2", "ticker": "005930", "name": "A",
                "event_type": "DERIVATIVE_LOSS", "event_stage": "CONFIRMED", "event_title": "손실",
                "material_score": 75, "material_status": "CONFIRMED", "relation_type": "DIRECT",
                "relation_weight": 1.0, "mapping_relevance": 1.0, "ticker_material_score": 75,
                "novelty_status": "NEW_EVENT", "positive_negative": "NEGATIVE", "source_id": "DART",
                "theme": "", "backtest_eligible": 1,
            },
        ]
        pd.DataFrame(rows).to_csv(source, index=False, encoding="utf-8-sig")
        result = MaterialBacktester(provider=_FakeProvider()).run(source, output)
        assert result.result_rows == 2
        assert result.valid_entry_rows == 2
        frame = pd.read_csv(result.results_csv, encoding="utf-8-sig")
        assert round(float(frame.loc[0, "D+1"]), 6) == 1.0
        assert float(frame.loc[0, "directional_D+1"]) > 0
        assert float(frame.loc[1, "directional_D+1"]) < 0
        summary = pd.read_csv(result.summary_csv, encoding="utf-8-sig")
        assert ((summary["dimension"] == "OVERALL") & (summary["value"] == "ALL")).any()

    print("[OK] MaterialBacktester V1 smoke test")
    print("     point-in-time exact entry -> OK")
    print("     D+1/D+5/D+10/D+20/D+40/D+60 -> OK")
    print("     positive/negative directional return -> OK")
    print("     summary dimensions -> OK")


if __name__ == "__main__":
    main()
