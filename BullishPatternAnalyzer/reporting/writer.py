from __future__ import annotations

from pathlib import Path
import pandas as pd
from core.models import Candidate


DETECTION_COLUMNS = [
    "date", "ticker", "name", "market", "pattern_type", "pattern_category", "pattern_state",
    "structure_score", "breakout_score", "volume_score", "candle_score", "momentum_score",
    "retest_score", "selection_score", "timing_score", "volume_filter_pass", "candle_signal",
    "volume_ratio", "market_regime", "entry_mode", "entry_date", "entry_price",
]


def _ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if not df.empty:
        return df
    return pd.DataFrame(columns=columns)


def write_daily(results_dir: Path, candidates: list[Candidate]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([c.as_record() for c in candidates])
    df = _ensure_columns(df, DETECTION_COLUMNS)
    df.to_csv(results_dir / "bullish_pattern_all.csv", index=False, encoding="utf-8-sig")
    confirmed_mask = df["pattern_state"].isin(["BREAKOUT_CONFIRMED", "RETEST", "ENTRY_READY"]) if "pattern_state" in df else pd.Series(False, index=df.index)
    volume_mask = df["volume_filter_pass"].fillna(False).astype(bool) if "volume_filter_pass" in df else pd.Series(False, index=df.index)
    confirmed = df[confirmed_mask & volume_mask]
    confirmed.to_csv(results_dir / "bullish_pattern_candidates.csv", index=False, encoding="utf-8-sig")
    watch = df[~(confirmed_mask & volume_mask)]
    watch.to_csv(results_dir / "bullish_pattern_watchlist.csv", index=False, encoding="utf-8-sig")
    with (results_dir / "summary.md").open("w", encoding="utf-8") as f:
        f.write(f"# BullishPatternAnalyzer Daily Summary\n\n- detected: {len(df)}\n- confirmed + volume filter: {len(confirmed)}\n- watch/rejected: {len(watch)}\n")
        if len(confirmed):
            cols = [c for c in ["ticker", "name", "pattern_type", "pattern_state", "selection_score", "timing_score", "volume_ratio", "candle_signal", "chase_risk", "entry_risk", "market_regime"] if c in confirmed]
            f.write("\n## Top confirmed candidates\n\n" + confirmed.sort_values(["selection_score", "timing_score"], ascending=False)[cols].head(20).to_markdown(index=False) + "\n")


def write_range(
    results_dir: Path,
    all_detections: pd.DataFrame,
    events: pd.DataFrame,
    perf_pattern: pd.DataFrame,
    perf_pattern_all: pd.DataFrame,
    perf_state: pd.DataFrame,
    perf_volume: pd.DataFrame,
    perf_market: pd.DataFrame,
    perf_condition: pd.DataFrame,
) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "range_all_detections.csv": _ensure_columns(all_detections, DETECTION_COLUMNS),
        "events.csv": _ensure_columns(events, DETECTION_COLUMNS),
        "performance_by_pattern.csv": _ensure_columns(perf_pattern, ["pattern_type", "events"]),
        "performance_by_pattern_all.csv": _ensure_columns(perf_pattern_all, ["pattern_type", "events"]),
        "performance_by_state.csv": _ensure_columns(perf_state, ["pattern_state", "events"]),
        "performance_by_volume.csv": _ensure_columns(perf_volume, ["volume_bucket", "events"]),
        "performance_by_market_regime.csv": _ensure_columns(perf_market, ["market_regime", "events"]),
        "performance_by_condition.csv": _ensure_columns(perf_condition, ["condition", "events", "share"]),
    }
    for name, df in outputs.items():
        df.to_csv(results_dir / name, index=False, encoding="utf-8-sig")

    with (results_dir / "range_summary.md").open("w", encoding="utf-8") as f:
        f.write("# BullishPatternAnalyzer Range Backtest V1.1\n\n")
        f.write(f"- all detections: {len(all_detections)}\n")
        f.write(f"- unique actionable events (volume-filtered): {len(events)}\n")
        f.write("- entry: next trading-day open\n")
        if not perf_pattern.empty:
            f.write("\n## Actionable performance by pattern\n\n" + perf_pattern.to_markdown(index=False) + "\n")
        if not perf_state.empty:
            f.write("\n## Performance by state\n\n" + perf_state.to_markdown(index=False) + "\n")
        if not perf_condition.empty:
            f.write("\n## Performance by confirmation condition\n\n" + perf_condition.to_markdown(index=False) + "\n")
