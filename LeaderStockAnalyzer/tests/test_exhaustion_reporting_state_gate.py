from copy import deepcopy

import pandas as pd

from leader_stock_analyzer.config import DEFAULT_CONFIG
from leader_stock_analyzer.exhaustion import ExhaustionTransitionAnalyzer


def test_high_risk_becomes_event_when_stock_enters_leader_state():
    cfg = deepcopy(DEFAULT_CONFIG)
    df = pd.DataFrame(
        [
            {
                "ticker": "111111",
                "scan_date": "20260820",
                "lifecycle_state": "EMERGING",
                "exhaustion_risk_label": "HIGH",
            },
            {
                "ticker": "111111",
                "scan_date": "20260821",
                "lifecycle_state": "LEADER",
                "exhaustion_risk_label": "HIGH",
                "D+20": -5.0,
            },
            {
                "ticker": "111111",
                "scan_date": "20260824",
                "lifecycle_state": "EXHAUSTING",
                "exhaustion_risk_label": "CRITICAL",
            },
        ]
    )

    events = ExhaustionTransitionAnalyzer(cfg).events(df)

    assert len(events) == 1
    assert events.iloc[0]["scan_date"] == "20260821"
    assert bool(events.iloc[0]["exhausting_within_3d"]) is True
