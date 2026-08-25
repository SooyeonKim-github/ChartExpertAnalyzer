from __future__ import annotations

from pathlib import Path
import pandas as pd
from core.models import Candidate


def write_daily(results_dir: Path, candidates: list[Candidate]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True); df = pd.DataFrame([c.as_record() for c in candidates])
    if df.empty: df = pd.DataFrame(columns=["date","ticker","name","market","pattern_type","pattern_state","selection_score","timing_score"])
    df.to_csv(results_dir/"bullish_pattern_all.csv", index=False, encoding="utf-8-sig")
    confirmed = df[df["pattern_state"].isin(["BREAKOUT_CONFIRMED","RETEST","ENTRY_READY"])] if "pattern_state" in df else df.iloc[0:0]; confirmed.to_csv(results_dir/"bullish_pattern_candidates.csv", index=False, encoding="utf-8-sig")
    watch = df[df["pattern_state"].isin(["FORMING","WATCH"])] if "pattern_state" in df else df.iloc[0:0]; watch.to_csv(results_dir/"bullish_pattern_watchlist.csv", index=False, encoding="utf-8-sig")
    with (results_dir/"summary.md").open("w",encoding="utf-8") as f:
        f.write(f"# BullishPatternAnalyzer Daily Summary\n\n- detected: {len(df)}\n- confirmed/entry: {len(confirmed)}\n- watch: {len(watch)}\n")
        if len(confirmed):
            cols=[c for c in ["ticker","name","pattern_type","pattern_state","selection_score","timing_score","chase_risk","entry_risk","market_regime"] if c in confirmed]; f.write("\n## Top confirmed candidates\n\n"+confirmed.sort_values(["selection_score","timing_score"],ascending=False)[cols].head(20).to_markdown(index=False)+"\n")


def write_range(results_dir: Path, events: pd.DataFrame, perf: pd.DataFrame) -> None:
    results_dir.mkdir(parents=True, exist_ok=True); events.to_csv(results_dir/"events.csv",index=False,encoding="utf-8-sig"); perf.to_csv(results_dir/"performance_by_pattern.csv",index=False,encoding="utf-8-sig")
    with (results_dir/"range_summary.md").open("w",encoding="utf-8") as f:
        f.write(f"# BullishPatternAnalyzer Range Backtest\n\n- events: {len(events)}\n")
        if not perf.empty: f.write("\n## Performance by pattern\n\n"+perf.to_markdown(index=False)+"\n")
