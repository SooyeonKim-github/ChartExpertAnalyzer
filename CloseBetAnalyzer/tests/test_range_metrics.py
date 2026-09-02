from __future__ import annotations

import pandas as pd

from CloseBetAnalyzer.main_range import _performance_metrics


def test_performance_metrics_use_signal_close_as_entry():
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    df = pd.DataFrame(
        {
            "Open": [100, 110, 120, 130],
            "High": [105, 120, 130, 140],
            "Low": [95, 105, 115, 125],
            "Close": [100, 115, 125, 135],
            "Volume": [1, 1, 1, 1],
        },
        index=idx,
    )
    out = _performance_metrics(df, pd.Timestamp("2026-01-02"), 100.0)
    assert round(out["D+1_Open_Return_Pct"], 6) == 10.0
    assert round(out["D+1_Close_Return_Pct"], 6) == 15.0
    assert round(out["MFE_1D_Pct"], 6) == 20.0
    assert round(out["MAE_1D_Pct"], 6) == 5.0
