from __future__ import annotations

"""Dynamic LONG V2.1 runner: lecture score and secondary quality score separated."""

import numpy as np
import pandas as pd

import main_range_v2 as _v2
from dynamic_chart_analyzer.long_v21 import score_long_events as _score_long_events_v21

# Expose the same patch points expected by main_range_kjb.py.
_latest_market_date = _v2._latest_market_date
_get_universe = _v2._get_universe
load_pykrx = _v2.load_pykrx


def _build_long_v21_summary(events: pd.DataFrame, forward_bars: int) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["long_quality_label", "stage", "count"])

    long_df = events[events["side"].eq("LONG")].copy()
    if long_df.empty:
        return pd.DataFrame(columns=["long_quality_label", "stage", "count"])

    horizons = [h for h in [1, 5, 10, 20, 40, 60] if h <= forward_bars]
    rows: list[dict] = []
    label_order = {"CONFIRMED": 0, "WATCH": 1, "REJECT": 2}

    for (label, stage), g in long_df.groupby(["long_quality_label", "stage"], dropna=False):
        row: dict[str, object] = {
            "long_quality_label": label,
            "stage": int(stage),
            "count": int(len(g)),
            "complete_count": int(g["forward_complete"].fillna(False).sum()),
            "avg_lecture_score": float(pd.to_numeric(g["lecture_score"], errors="coerce").mean()),
            "avg_quality_score": float(pd.to_numeric(g["quality_score"], errors="coerce").mean()),
            "avg_combined_score": float(pd.to_numeric(g["combined_score"], errors="coerce").mean()),
        }
        for h in horizons:
            col = f"D+{h}"
            vals = pd.to_numeric(g[col], errors="coerce").dropna()
            row[f"avg_{col}"] = float(vals.mean()) if len(vals) else np.nan
            row[f"median_{col}"] = float(vals.median()) if len(vals) else np.nan
            row[f"win_rate_{col}"] = float((vals > 0).mean()) if len(vals) else np.nan

        mfe_col = f"MFE_D+{forward_bars}"
        mae_col = f"MAE_D+{forward_bars}"
        row[f"avg_{mfe_col}"] = float(pd.to_numeric(g[mfe_col], errors="coerce").mean())
        row[f"avg_{mae_col}"] = float(pd.to_numeric(g[mae_col], errors="coerce").mean())
        rows.append(row)

    out = pd.DataFrame(rows)
    out["_label_order"] = out["long_quality_label"].map(label_order).fillna(99)
    return (
        out.sort_values(["_label_order", "stage"])
        .drop(columns="_label_order")
        .reset_index(drop=True)
    )


def run_range(args) -> int:
    # Apply V2.1 behavior to the existing V2 range engine.
    _v2.score_long_events = _score_long_events_v21
    _v2._build_long_v2_summary = _build_long_v21_summary

    # main_range_kjb.py patches these globals on this wrapper. Propagate them to V2.
    _v2._latest_market_date = _latest_market_date
    _v2._get_universe = _get_universe

    print("[INFO] Dynamic LONG V2.1: Stage / Lecture / Quality are separated")
    print("[INFO] lecture_score=0..100 (RSI/MACD/Ichimoku only)")
    print("[INFO] quality_score=0..100 (Trend/RS/Volume/Structure/Market/Risk)")
    print("[INFO] CONFIRMED/WATCH/REJECT and daily rank use quality_score only")
    return _v2.run_range(args)


def build_parser():
    p = _v2.build_parser()
    p.description = "DynamicChartAnalyzer TOP-N range backtest V2.1 (lecture/quality split)"
    return p


if __name__ == "__main__":
    raise SystemExit(run_range(build_parser().parse_args()))
