from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MILESTONES = (5, 10, 20, 60)


def _parse_range(text: str) -> tuple[str, str]:
    raw = str(text or "").strip().replace("-", "").replace(" ", "")
    if "~" not in raw:
        raise ValueError("date range must be YYYYMMDD~YYYYMMDD")
    start, end = raw.split("~", 1)
    pd.to_datetime(start, format="%Y%m%d", errors="raise")
    pd.to_datetime(end, format="%Y%m%d", errors="raise")
    return start, end


def _ticker(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text else ""


def _num(value):
    try:
        if pd.isna(value):
            return np.nan
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"[WARN] source not found: {path}")
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def _base_row(*, signal_date, analyzer: str, ticker, name, status, score=np.nan,
              timing_score=np.nan, market="", signal="", pattern_type="", source_file: Path,
              position_action="", entry_stage=np.nan) -> dict:
    return {
        "signal_date": _text(signal_date), "analyzer": analyzer, "ticker": _ticker(ticker),
        "name": _text(name), "status": _text(status), "score": _num(score),
        "timing_score": _num(timing_score), "market": _text(market), "signal": _text(signal),
        "pattern_type": _text(pattern_type), "position_action": _text(position_action),
        "entry_stage": _num(entry_stage), "D+5_Pct": np.nan, "D+10_Pct": np.nan,
        "D+20_Pct": np.nan, "D+60_Pct": np.nan,
        "source_file": str(source_file.relative_to(ROOT)),
    }


def _load_kjb(path: Path) -> list[dict]:
    df = _read_csv(path)
    if df.empty or "Status" not in df.columns:
        return []
    rows = []
    for _, r in df[df["Status"].astype(str).str.upper().eq("CONFIRMED")].iterrows():
        row = _base_row(signal_date=r.get("signal_date", ""), analyzer="KJB", ticker=r.get("ticker", ""),
            name=r.get("name", ""), status="CONFIRMED", score=r.get("selection_score", np.nan),
            timing_score=r.get("timing_score", np.nan), market=r.get("market", ""),
            signal=r.get("entry_status", ""), source_file=path)
        for h in MILESTONES:
            value = _num(r.get(f"D+{h}", np.nan))
            row[f"D+{h}_Pct"] = value * 100.0 if pd.notna(value) else np.nan
        rows.append(row)
    return rows


def _load_swing(path: Path) -> list[dict]:
    df = _read_csv(path)
    if df.empty or "Status" not in df.columns:
        return []
    selected = df[df["Status"].astype(str).str.upper().isin(["STRONG_CONFIRMED", "CONFIRMED"])]
    rows = []
    for _, r in selected.iterrows():
        status = _text(r.get("Status", "")).upper()
        row = _base_row(signal_date=r.get("Actual_Date", ""), analyzer="SWING", ticker=r.get("Ticker", ""),
            name=r.get("Name", ""), status=status, score=r.get("Score", np.nan),
            market=r.get("Market", ""), signal=r.get("Primary_Signal", ""), source_file=path)
        for h in MILESTONES:
            row[f"D+{h}_Pct"] = _num(r.get(f"D+{h}_Close_Return_Pct", np.nan))
        rows.append(row)
    return rows


def _load_ma(path: Path) -> list[dict]:
    df = _read_csv(path)
    if df.empty or "Status" not in df.columns:
        return []
    selected = df[df["Status"].astype(str).str.upper().isin(["STRONG_CONFIRMED", "CONFIRMED"])].copy()
    rows = []
    for _, r in selected.iterrows():
        status = _text(r.get("Status", "")).upper()
        row = _base_row(signal_date=r.get("Actual_Date", ""), analyzer="MA", ticker=r.get("Ticker", ""),
            name=r.get("Name", ""), status=status, score=r.get("Score", np.nan),
            timing_score=r.get("Timing_Score", np.nan), market=r.get("Market", ""),
            signal=r.get("Primary_Signal", ""), source_file=path,
            position_action=r.get("Position_Action", ""), entry_stage=r.get("Entry_Stage", np.nan))
        for h in MILESTONES:
            row[f"D+{h}_Pct"] = _num(r.get(f"D+{h}_Close_Return_Pct", np.nan))
        rows.append(row)
    return rows


def _load_dynamic(path: Path) -> list[dict]:
    df = _read_csv(path)
    if df.empty or "long_quality_label" not in df.columns:
        return []
    if "side" not in df.columns:
        return []
    selected = df[
        df["side"].astype(str).str.upper().eq("LONG")
        & df["long_quality_label"].astype(str).str.upper().eq("CONFIRMED")
    ].copy()
    rows = []
    for _, r in selected.iterrows():
        row = _base_row(
            signal_date=r.get("signal_date", ""), analyzer="DYNAMIC", ticker=r.get("ticker", ""),
            name=r.get("name", ""), status="CONFIRMED", score=r.get("quality_score", np.nan),
            timing_score=r.get("lecture_score", np.nan), market=r.get("market", ""),
            signal=r.get("action", ""), source_file=path,
            position_action=r.get("action", ""), entry_stage=r.get("stage", np.nan),
        )
        for h in MILESTONES:
            value = _num(r.get(f"D+{h}", np.nan))
            row[f"D+{h}_Pct"] = value * 100.0 if pd.notna(value) else np.nan
        rows.append(row)
    return rows


def _dedupe_within_analyzer(rows: list[dict]) -> list[dict]:
    best = {}
    for row in rows:
        key = (row["analyzer"], row["signal_date"], row["ticker"])
        old = best.get(key)
        if old is None:
            best[key] = row
            continue
        new_rank = (-1e18 if pd.isna(row["score"]) else row["score"], -1e18 if pd.isna(row["timing_score"]) else row["timing_score"])
        old_rank = (-1e18 if pd.isna(old["score"]) else old["score"], -1e18 if pd.isna(old["timing_score"]) else old["timing_score"])
        if new_rank > old_rank:
            best[key] = row
    return list(best.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect independent confirmed range signals from KJB, Swing, MA, and Dynamic")
    parser.add_argument("--date-range", required=True)
    args = parser.parse_args()
    start, end = _parse_range(args.date_range)
    range_key = f"{start}_{end}"
    kjb_path = ROOT / "KJBChartAnalyzer" / "results" / f"range_{range_key}" / "chart_range_events.csv"
    swing_path = ROOT / "SwingChartProbabilityAnalyzer" / "results" / f"range_{range_key}" / "range_all_results.csv"
    ma_path = ROOT / "MAChartAnalyzer" / "results" / f"range_{range_key}" / "range_all_results.csv"
    dynamic_path = ROOT / "DynamicChartAnalyzer" / "results" / f"range_{range_key}" / "dynamic_long_v2_candidates.csv"
    rows = _dedupe_within_analyzer(
        _load_kjb(kjb_path)
        + _load_swing(swing_path)
        + _load_ma(ma_path)
        + _load_dynamic(dynamic_path)
    )
    status_rank = {"STRONG_CONFIRMED": 0, "CONFIRMED": 1}
    rows.sort(key=lambda r: (r["signal_date"], status_rank.get(r["status"], 9), r["analyzer"], -(r["score"] if pd.notna(r["score"]) else -1e18), r["ticker"]))
    out_dir = ROOT / "results" / f"range_{range_key}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "confirmed_candidates.csv"
    columns = ["signal_date", "analyzer", "ticker", "name", "status", "score", "timing_score", "market", "signal",
        "pattern_type", "position_action", "entry_stage", "D+5_Pct", "D+10_Pct", "D+20_Pct", "D+60_Pct", "source_file"]
    pd.DataFrame(rows, columns=columns).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[DONE] Independent confirmed candidates: {len(rows)} -> {out_path}")
    if rows:
        counts = pd.DataFrame(rows)["analyzer"].value_counts()
        for analyzer in ("KJB", "SWING", "MA", "DYNAMIC"):
            print(f"[INFO] {analyzer}: {int(counts.get(analyzer, 0))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
