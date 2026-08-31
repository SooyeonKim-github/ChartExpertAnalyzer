from __future__ import annotations

"""Dynamic LONG V2.2 runner.

Lecture timing remains the V2.1 axis.  V2.2 changes only the secondary quality
ranking overlay using data-informed broad sweet spots, while market regime remains
context-only rather than a hard directional score.
"""

import main_range_v2 as _v2
from dynamic_chart_analyzer.long_v22 import score_long_events as _score_long_events_v22
from main_range_v21 import _build_long_v21_summary

# Expose the same patch points expected by main_range_kjb.py.
_latest_market_date = _v2._latest_market_date
_get_universe = _v2._get_universe
load_pykrx = _v2.load_pykrx


def run_range(args) -> int:
    _v2.score_long_events = _score_long_events_v22
    _v2._build_long_v2_summary = _build_long_v21_summary

    # main_range_kjb.py patches these globals on this wrapper. Propagate to V2.
    _v2._latest_market_date = _latest_market_date
    _v2._get_universe = _get_universe

    print("[INFO] Dynamic LONG V2.2: lecture timing preserved, quality overlay revised")
    print("[INFO] lecture_score: RSI/MACD/Ichimoku only; unchanged from V2.1")
    print("[INFO] quality_score weights: RS25 / Trend20 / Structure15 / Volume15 / Market10 / Risk15")
    print("[INFO] market context: REVERSAL_ENV / NEUTRAL_ENV / TREND_ENV; no bull/bear reverse scoring")
    print("[INFO] CONFIRMED/WATCH/REJECT and daily rank use quality_score only")
    return _v2.run_range(args)


def build_parser():
    p = _v2.build_parser()
    p.description = "DynamicChartAnalyzer TOP-N range backtest V2.2 (lecture-preserving quality overlay)"
    return p


if __name__ == "__main__":
    raise SystemExit(run_range(build_parser().parse_args()))
