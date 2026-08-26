from __future__ import annotations

from pathlib import Path
import pandas as pd
from core.models import Candidate


DETECTION_COLUMNS = [
    "date",
    "ticker",
    "name",
    "market",
    "pattern_type",
    "pattern_category",
    "pattern_state",
    "decision_status",
    "reject_reason",
    "structure_score",
    "breakout_score",
    "volume_score",
    "candle_score",
    "momentum_score",
    "retest_score",
    "selection_score",
    "timing_score",
    "volume_filter_pass",
    "candle_signal",
    "volume_ratio",
    "market_regime",
    "entry_mode",
    "entry_date",
    "entry_price",
]


def _ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if not df.empty:
        return df
    return pd.DataFrame(columns=columns)


def write_daily(results_dir: Path, candidates: list[Candidate]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([c.as_record() for c in candidates])
    df = _ensure_columns(df, DETECTION_COLUMNS)
    df.to_csv(
        results_dir / "bullish_pattern_all.csv", index=False, encoding="utf-8-sig"
    )

    confirmed = (
        df[df["decision_status"] == "CONFIRMED"]
        if "decision_status" in df
        else df.iloc[0:0]
    )
    watch = (
        df[df["decision_status"] == "WATCH"]
        if "decision_status" in df
        else df.iloc[0:0]
    )
    rejected = (
        df[df["decision_status"] == "REJECT"]
        if "decision_status" in df
        else df.iloc[0:0]
    )

    confirmed.to_csv(
        results_dir / "bullish_pattern_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    watch.to_csv(
        results_dir / "bullish_pattern_watchlist.csv",
        index=False,
        encoding="utf-8-sig",
    )
    rejected.to_csv(
        results_dir / "bullish_pattern_rejected.csv",
        index=False,
        encoding="utf-8-sig",
    )

    with (results_dir / "summary.md").open("w", encoding="utf-8") as f:
        f.write("# BullishPatternAnalyzer Daily Summary\n\n")
        f.write(f"- detected: {len(df)}\n")
        f.write(f"- CONFIRMED: {len(confirmed)}\n")
        f.write(f"- WATCH: {len(watch)}\n")
        f.write(f"- REJECT: {len(rejected)}\n")
        if len(confirmed):
            cols = [
                c
                for c in [
                    "ticker",
                    "name",
                    "pattern_type",
                    "pattern_state",
                    "decision_status",
                    "selection_score",
                    "timing_score",
                    "volume_ratio",
                    "candle_signal",
                    "chase_risk",
                    "entry_risk",
                    "market_regime",
                ]
                if c in confirmed
            ]
            f.write(
                "\n## Top confirmed candidates\n\n"
                + confirmed.sort_values(
                    ["selection_score", "timing_score"], ascending=False
                )[cols]
                .head(20)
                .to_markdown(index=False)
                + "\n"
            )
        if len(rejected):
            cols = [
                c
                for c in [
                    "ticker",
                    "name",
                    "pattern_type",
                    "reject_reason",
                    "selection_score",
                    "timing_score",
                    "market_regime",
                ]
                if c in rejected
            ]
            f.write(
                "\n## Rejected\n\n"
                + rejected[cols].head(20).to_markdown(index=False)
                + "\n"
            )


def write_range(
    results_dir: Path,
    all_detections: pd.DataFrame,
    events: pd.DataFrame,
    perf_pattern: pd.DataFrame,
    perf_pattern_all: pd.DataFrame,
    perf_state: pd.DataFrame,
    perf_decision: pd.DataFrame,
    perf_volume: pd.DataFrame,
    perf_market: pd.DataFrame,
    perf_condition: pd.DataFrame,
) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)

    if all_detections.empty:
        watch = pd.DataFrame()
        rejected = pd.DataFrame()
    else:
        watch = all_detections[
            all_detections["decision_status"] == "WATCH"
        ].copy()
        rejected = all_detections[
            all_detections["decision_status"] == "REJECT"
        ].copy()

    outputs = {
        "range_all_detections.csv": _ensure_columns(
            all_detections, DETECTION_COLUMNS
        ),
        "events.csv": _ensure_columns(events, DETECTION_COLUMNS),
        "range_watch.csv": _ensure_columns(watch, DETECTION_COLUMNS),
        "range_rejected.csv": _ensure_columns(rejected, DETECTION_COLUMNS),
        "performance_by_pattern.csv": _ensure_columns(
            perf_pattern, ["pattern_type", "events"]
        ),
        "performance_by_pattern_all.csv": _ensure_columns(
            perf_pattern_all, ["pattern_type", "events"]
        ),
        "performance_by_state.csv": _ensure_columns(
            perf_state, ["pattern_state", "events"]
        ),
        "performance_by_decision.csv": _ensure_columns(
            perf_decision, ["decision_status", "events"]
        ),
        "performance_by_volume.csv": _ensure_columns(
            perf_volume, ["volume_bucket", "events"]
        ),
        "performance_by_market_regime.csv": _ensure_columns(
            perf_market, ["market_regime", "events"]
        ),
        "performance_by_condition.csv": _ensure_columns(
            perf_condition, ["condition", "events", "share"]
        ),
    }
    for name, df in outputs.items():
        df.to_csv(results_dir / name, index=False, encoding="utf-8-sig")

    confirmed_count = (
        int((all_detections["decision_status"] == "CONFIRMED").sum())
        if not all_detections.empty and "decision_status" in all_detections
        else 0
    )
    watch_count = (
        int((all_detections["decision_status"] == "WATCH").sum())
        if not all_detections.empty and "decision_status" in all_detections
        else 0
    )
    reject_count = (
        int((all_detections["decision_status"] == "REJECT").sum())
        if not all_detections.empty and "decision_status" in all_detections
        else 0
    )

    with (results_dir / "range_summary.md").open("w", encoding="utf-8") as f:
        f.write("# BullishPatternAnalyzer Range Backtest V1.1\n\n")
        f.write(f"- all detections: {len(all_detections)}\n")
        f.write(f"- CONFIRMED: {confirmed_count}\n")
        f.write(f"- WATCH: {watch_count}\n")
        f.write(f"- REJECT: {reject_count}\n")
        f.write(f"- unique actionable events after cooldown: {len(events)}\n")
        f.write("- entry: next trading-day open\n")
        if not perf_pattern.empty:
            f.write(
                "\n## Actionable performance by pattern\n\n"
                + perf_pattern.to_markdown(index=False)
                + "\n"
            )
        if not perf_decision.empty:
            f.write(
                "\n## Performance by decision\n\n"
                + perf_decision.to_markdown(index=False)
                + "\n"
            )
        if not perf_state.empty:
            f.write(
                "\n## Performance by state\n\n"
                + perf_state.to_markdown(index=False)
                + "\n"
            )
        if not perf_condition.empty:
            f.write(
                "\n## Performance by confirmation condition\n\n"
                + perf_condition.to_markdown(index=False)
                + "\n"
            )
