import numpy as np
import pandas as pd

from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.performance import ForwardPerformanceEngine, PerformanceAttributionEngine


def _future_daily():
    n = 70
    idx = pd.bdate_range("2026-01-02", periods=n)
    close = np.linspace(100.0, 130.0, n)
    high = close + 2.0
    low = close - 2.0
    open_ = close - 0.5
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=idx,
    )


def test_forward_performance_uses_future_high_low_and_trading_rows():
    engine = ForwardPerformanceEngine(DEFAULT_CONFIG)
    df = _future_daily()
    scan_date = df.index[0].strftime("%Y%m%d")
    result = engine.evaluate(df, scan_date, breakout_reference=99.0)

    assert result["D+5"] is not None
    assert result["D+20"] is not None
    assert result["MFE_D20"] is not None and result["MFE_D20"] > result["D+20"]
    assert result["MAE_D20"] is not None
    assert 1 <= result["days_to_MFE_D20"] <= 20
    assert 1 <= result["days_to_MAE_D20"] <= 20
    assert result["breakout_hold_D1"] is True
    assert result["breakout_hold_D3"] is True
    assert result["failed_within_D3"] is False


def test_incomplete_horizon_is_none():
    engine = ForwardPerformanceEngine(DEFAULT_CONFIG)
    df = _future_daily().iloc[:10]
    scan_date = df.index[0].strftime("%Y%m%d")
    result = engine.evaluate(df, scan_date)
    assert result["D+20"] is None
    assert result["MFE_D20"] is None
    assert result["MAE_D20"] is None


def test_attribution_builds_expected_reports():
    cfg = dict(DEFAULT_CONFIG)
    cfg["performance"] = dict(DEFAULT_CONFIG["performance"])
    cfg["performance"]["min_group_count"] = 2
    engine = PerformanceAttributionEngine(cfg)
    df = pd.DataFrame(
        {
            "status": ["CONFIRMED", "CONFIRMED", "WATCH"],
            "breakout_quality_label": ["CLEAN_BREAKOUT", "VALID_BREAKOUT", "WEAK_BREAKOUT"],
            "leader_type": ["PERSISTENT_LEADER", "EMERGING_LEADER", "NORMAL"],
            "sector_market_rank": [2, 4, 15],
            "leader_persistence_level": ["HIGH", "LOW", "MEDIUM"],
            "leader_persistence_score": [82, 32, 55],
            "leader_score": [90, 86, 70],
            "timing_score": [80, 77, 60],
            "chase_risk": [30, 45, 65],
            "D+5": [3.0, 2.0, -1.0],
            "D+20": [10.0, 6.0, -4.0],
            "D+60": [15.0, 8.0, -5.0],
            "MFE_D20": [18.0, 12.0, 5.0],
            "MAE_D20": [-3.0, -5.0, -9.0],
            "excursion_ratio_D20": [6.0, 2.4, 0.56],
            "mfe_capture_D20": [0.56, 0.5, -0.8],
            "failed_within_D3": [False, False, True],
        }
    )
    reports = engine.build_reports(df)
    assert "performance_by_breakout_quality" in reports
    assert "performance_by_combinations" in reports
    status = reports["performance_by_status"]
    confirmed = status[status["status"] == "CONFIRMED"].iloc[0]
    assert confirmed["count"] == 2
    assert confirmed["sample_quality"] == "OK"
