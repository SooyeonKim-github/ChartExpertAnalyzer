from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from backtest.event_backtester import (
    EventBacktester,
    performance_by_condition,
    performance_by_market_regime,
    performance_by_pattern,
    performance_by_state,
    performance_by_volume,
)
from config import BACKTEST
from data.data_provider import PyKrxDataProvider
from reporting.writer import write_range
from services.scanner import BullishPatternScanner


def parse_range(v: str):
    a, b = v.replace("-", "").split("~", 1)
    return pd.Timestamp(a), pd.Timestamp(b)


def main() -> None:
    p = argparse.ArgumentParser(description="Bullish chart-pattern range backtest V1.1")
    p.add_argument("--date-range", required=True)
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--daily-candidate-top-n", type=int, default=BACKTEST.daily_candidate_top_n)
    p.add_argument("--event-cooldown-sessions", type=int, default=BACKTEST.event_cooldown_sessions)
    a = p.parse_args()

    start, end = parse_range(a.date_range)
    provider = PyKrxDataProvider()
    scanner = BullishPatternScanner(provider)
    all_candidates = []
    selected_keys: set[tuple[str, str, str]] = set()
    last_event_session: dict[tuple[str, str], int] = {}
    dates = provider.trading_dates(start.strftime("%Y%m%d"), end.strftime("%Y%m%d")) or [x.strftime("%Y%m%d") for x in pd.bdate_range(start, end)]

    for session_no, date in enumerate(dates):
        try:
            day = scanner.scan(date, a.top_n)
        except Exception as exc:
            print(f"[WARN] {date}: {exc}")
            continue
        all_candidates.extend(day)
        actionable = [c for c in day if c.volume_filter_pass and c.pattern_state.value in {"BREAKOUT_CONFIRMED", "RETEST", "ENTRY_READY"}]
        kept = []
        for c in actionable:
            key = (c.ticker, c.pattern_type.value)
            prev = last_event_session.get(key)
            if prev is not None and session_no - prev < a.event_cooldown_sessions:
                continue
            kept.append(c)
            last_event_session[key] = session_no
            if len(kept) >= a.daily_candidate_top_n:
                break
        for c in kept:
            selected_keys.add((c.date, c.ticker, c.pattern_type.value))
        print(f"[{date}] detected={len(day)} actionable={len(actionable)} unique_kept={len(kept)}")

    backtester = EventBacktester(provider)
    all_df = backtester.enrich(all_candidates)
    if all_df.empty:
        events = pd.DataFrame()
    else:
        signal_keys = all_df.apply(lambda r: (str(r.get("date")), str(r.get("ticker")).zfill(6), str(r.get("pattern_type"))), axis=1)
        events = all_df[signal_keys.isin(selected_keys)].copy()

    perf_pattern = performance_by_pattern(events)
    perf_pattern_all = performance_by_pattern(all_df)
    perf_state = performance_by_state(all_df)
    perf_volume = performance_by_volume(all_df)
    perf_market = performance_by_market_regime(all_df)
    perf_condition = performance_by_condition(all_df)

    out = Path(__file__).resolve().parent / "results" / f"range_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
    write_range(out, all_df, events, perf_pattern, perf_pattern_all, perf_state, perf_volume, perf_market, perf_condition)
    print(f"[DONE] detections={len(all_df)} unique_events={len(events)} -> {out}")


if __name__ == "__main__":
    main()
