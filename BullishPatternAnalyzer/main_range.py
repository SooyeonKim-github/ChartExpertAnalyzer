from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
from backtest.event_backtester import EventBacktester, performance_by_pattern
from data.data_provider import PyKrxDataProvider
from reporting.writer import write_range
from services.scanner import BullishPatternScanner


def parse_range(v:str):
    a,b=v.replace("-","").split("~",1); return pd.Timestamp(a),pd.Timestamp(b)


def main() -> None:
    p=argparse.ArgumentParser(description="Bullish chart-pattern range backtest"); p.add_argument("--date-range",required=True); p.add_argument("--top-n",type=int,default=100); p.add_argument("--daily-candidate-top-n",type=int,default=20); a=p.parse_args(); start,end=parse_range(a.date_range); provider=PyKrxDataProvider(); scanner=BullishPatternScanner(provider); selected=[]; dates=provider.trading_dates(start.strftime("%Y%m%d"),end.strftime("%Y%m%d")) or [x.strftime("%Y%m%d") for x in pd.bdate_range(start,end)]
    for date in dates:
        try: day=scanner.scan(date,a.top_n)
        except Exception as exc: print(f"[WARN] {date}: {exc}"); continue
        actionable=[c for c in day if c.pattern_state.value in {"BREAKOUT_CONFIRMED","RETEST","ENTRY_READY"}]; selected.extend(actionable[:a.daily_candidate_top_n]); print(f"[{date}] detected={len(day)} actionable={len(actionable)}")
    events=EventBacktester(provider).enrich(selected); perf=performance_by_pattern(events); out=Path(__file__).resolve().parent/"results"/f"range_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"; write_range(out,events,perf); print(f"[DONE] {len(events)} events -> {out}")


if __name__ == "__main__": main()
