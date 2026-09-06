from copy import deepcopy

import pandas as pd

from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.emerging_reporting import EmergingTransitionAnalyzerV12


def test_lifecycle_reversion_is_not_same_as_price_failure():
    cfg = deepcopy(DEFAULT_CONFIG)
    df = pd.DataFrame(
        [
            {
                "ticker": "111111",
                "scan_date": "20260820",
                "true_emerging_flag": True,
                "lifecycle_state": "EMERGING",
                "lifecycle_prev_state": "DISCOVERY",
                "lifecycle_days_in_state": 1,
                "lifecycle_reason": "confirmed_rank_velocity_emerging",
                "D+20": 20.0,
            },
            {
                "ticker": "111111",
                "scan_date": "20260821",
                "true_emerging_flag": False,
                "lifecycle_state": "DISCOVERY",
                "lifecycle_prev_state": "EMERGING",
                "lifecycle_days_in_state": 1,
                "lifecycle_reason": "confirmed_emerging_hold_failure",
                "D+20": 10.0,
            },
        ]
    )

    reporter = EmergingTransitionAnalyzerV12(cfg)
    events = reporter.events(df)
    summary = reporter.summary(events)

    assert len(events) == 1
    event = events.iloc[0]
    assert bool(event["lifecycle_reversion_within_3d"]) is True
    assert bool(event["price_failure_D20"]) is False
    assert bool(event["strong_price_success_D20"]) is True

    row = summary[summary["cohort"].eq("RANK_VELOCITY_CONFIRMED")].iloc[0]
    assert row["lifecycle_reversion_within_3d_rate"] == 100.0
    assert row["price_failure_D20_rate"] == 0.0
    assert row["strong_price_success_D20_rate"] == 100.0
