from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RESULT_DIR = BASE_DIR / "results"

# Threshold optimization only needs the signal date, rule metrics and forward outcomes.
# Price-by-price D+1..D+60 columns, chart workbooks and agent exports are intentionally excluded.
KEEP_COLUMNS = [
    "Ticker",
    "Name",
    "Actual_Date",
    "Status",
    "Score",
    "Primary_Signal",
    "Uptrend_HH_HL",
    "Pullback_Pct",
    "Prior_Low_Held",
    "Channel_Coverage",
    "Channel_Position",
    "Recent_Lower_Touch",
    "Room_To_Mid_Pct",
    "Room_To_Upper_Pct",
    "Double_Bottom",
    "Double_Bottom_Confirmed",
    "MA_Clustered",
    "MA_Spread_Pct",
    "MA_Reclaimed",
    "MA5_Held",
    "Bottom_Volume_Surge",
    "Reference_Low_Held",
    "Reference_High_Break",
    "Reference_Volume_Ratio",
    "D+5_Close_Return_Pct",
    "D+10_Close_Return_Pct",
    "D+20_Close_Return_Pct",
    "D+40_Close_Return_Pct",
    "D+60_Close_Return_Pct",
    "MFE_20D_Pct",
    "MAE_20D_Pct",
    "MFE_60D_Pct",
    "MAE_60D_Pct",
    "Positive_D20",
    "Hit_Mid_Before_Stop",
    "Hit_PriorHigh_Before_Stop",
    "Hit_Upper_Before_Stop",
    "Stop_Hit",
    "First_Event",
]

CANDIDATE_STATUSES = {"STRONG_CONFIRMED", "CONFIRMED", "WATCH"}


def _latest_range_file() -> Path:
    files = list(RESULT_DIR.glob("range_*/range_all_results.csv"))
    if not files:
        raise FileNotFoundError(
            "No range_all_results.csv found under SwingChartProbabilityAnalyzer/results."
        )
    return max(files, key=lambda p: p.stat().st_mtime)


def _resolve_source(value: str | None) -> Path:
    if not value:
        return _latest_range_file()

    p = Path(value)
    if not p.is_absolute():
        direct = BASE_DIR / p
        under_results = RESULT_DIR / p
        if direct.exists():
            p = direct
        elif under_results.exists():
            p = under_results

    if p.is_dir():
        p = p / "range_all_results.csv"

    if not p.exists():
        raise FileNotFoundError(f"Range CSV not found: {p}")
    return p


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "y"})
    )


def _potential_mask(df: pd.DataFrame, min_score: float) -> pd.Series:
    """Keep rows that can realistically enter the planned threshold search.

    The Swing strategy treats uptrend/prior-low/recent-lower-touch as structural
    gates. Score and channel-position thresholds are the values we want to tune,
    so rejected rows that still satisfy the structural gates are intentionally kept.
    Existing WATCH/CONFIRMED rows are always preserved as a safety net.
    """

    score = pd.to_numeric(df.get("Score"), errors="coerce")
    uptrend = _as_bool(df.get("Uptrend_HH_HL", pd.Series(False, index=df.index)))
    prior_low = _as_bool(df.get("Prior_Low_Held", pd.Series(False, index=df.index)))
    lower_touch = _as_bool(df.get("Recent_Lower_Touch", pd.Series(False, index=df.index)))
    current_candidate = df.get("Status", pd.Series("", index=df.index)).astype(str).isin(
        CANDIDATE_STATUSES
    )

    potential = (
        (score >= float(min_score))
        & uptrend
        & prior_low
        & lower_touch
    )
    return (potential | current_candidate).fillna(False)


def _write_part(df: pd.DataFrame, out_dir: Path, part_no: int, max_file_mb: float) -> dict:
    path = out_dir / f"threshold_input_part_{part_no:03d}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    size_bytes = path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > max_file_mb:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Generated shard would be {size_mb:.1f} MB (> {max_file_mb:.1f} MB). "
            "Re-run with a smaller --rows-per-file value."
        )

    dates = pd.to_datetime(df.get("Actual_Date"), errors="coerce")
    scores = pd.to_numeric(df.get("Score"), errors="coerce")
    return {
        "file": path.name,
        "rows": int(len(df)),
        "bytes": int(size_bytes),
        "size_mb": round(size_mb, 3),
        "start_date": dates.min().strftime("%Y-%m-%d") if dates.notna().any() else "",
        "end_date": dates.max().strftime("%Y-%m-%d") if dates.notna().any() else "",
        "min_score": float(scores.min()) if scores.notna().any() else None,
        "max_score": float(scores.max()) if scores.notna().any() else None,
    }


def export_dataset(
    source: Path,
    out_dir: Path,
    *,
    min_score: float,
    chunksize: int,
    rows_per_file: int,
    max_file_mb: float,
) -> None:
    header = pd.read_csv(source, nrows=0, encoding="utf-8-sig")
    available = set(header.columns)
    selected_columns = [c for c in KEEP_COLUMNS if c in available]

    required = {"Actual_Date", "Status", "Score", "Primary_Signal"}
    missing_required = sorted(required - set(selected_columns))
    if missing_required:
        raise ValueError(
            "Range CSV is missing required columns: " + ", ".join(missing_required)
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("threshold_input_part_*.csv"):
        old.unlink()
    for old_name in ("manifest.csv", "metadata.json"):
        (out_dir / old_name).unlink(missing_ok=True)

    scanned_rows = 0
    exported_rows = 0
    part_no = 0
    manifest: list[dict] = []
    pending = pd.DataFrame(columns=selected_columns)

    reader = pd.read_csv(
        source,
        encoding="utf-8-sig",
        usecols=selected_columns,
        chunksize=chunksize,
        low_memory=False,
        dtype={"Ticker": str} if "Ticker" in selected_columns else None,
    )

    for chunk in reader:
        scanned_rows += len(chunk)
        chunk = chunk.loc[_potential_mask(chunk, min_score), selected_columns].copy()
        if chunk.empty:
            continue

        exported_rows += len(chunk)
        pending = pd.concat([pending, chunk], ignore_index=True)

        while len(pending) >= rows_per_file:
            part_no += 1
            piece = pending.iloc[:rows_per_file].copy()
            pending = pending.iloc[rows_per_file:].reset_index(drop=True)
            manifest.append(_write_part(piece, out_dir, part_no, max_file_mb))
            print(
                f"[WRITE] part={part_no:03d} rows={len(piece):,} "
                f"size={manifest[-1]['size_mb']:.1f} MB"
            )

        print(
            f"[READ] scanned={scanned_rows:,} exported={exported_rows:,} "
            f"pending={len(pending):,}"
        )

    if not pending.empty:
        part_no += 1
        manifest.append(_write_part(pending, out_dir, part_no, max_file_mb))
        print(
            f"[WRITE] part={part_no:03d} rows={len(pending):,} "
            f"size={manifest[-1]['size_mb']:.1f} MB"
        )

    pd.DataFrame(manifest).to_csv(out_dir / "manifest.csv", index=False, encoding="utf-8-sig")

    missing_optional = [c for c in KEEP_COLUMNS if c not in available]
    metadata = {
        "source": str(source),
        "source_size_mb": round(source.stat().st_size / (1024 * 1024), 3),
        "scanned_rows": int(scanned_rows),
        "exported_rows": int(exported_rows),
        "export_ratio": round(exported_rows / scanned_rows, 6) if scanned_rows else 0.0,
        "min_score": float(min_score),
        "rows_per_file": int(rows_per_file),
        "part_count": int(part_no),
        "columns": selected_columns,
        "missing_optional_columns": missing_optional,
        "filter": (
            "(Score >= min_score AND Uptrend_HH_HL AND Prior_Low_Held "
            "AND Recent_Lower_Touch) OR current Status in CONFIRMED/WATCH"
        ),
        "notes": [
            "This dataset is intentionally broader than current CONFIRMED rows so score/channel thresholds can be re-evaluated.",
            "Raw range_all_results.csv and swing_range_backtest.xlsx are not required for threshold optimization.",
            "Older range outputs may not contain Bullish_Turn/Channel_Breakdown flags; exact full-rule reconstruction will be handled separately if needed.",
        ],
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n============================================")
    print(" Swing Threshold Dataset Export complete")
    print("============================================")
    print(f"Source       : {source}")
    print(f"Output       : {out_dir}")
    print(f"Scanned rows : {scanned_rows:,}")
    print(f"Exported rows: {exported_rows:,}")
    print(f"Parts        : {part_no}")
    print("Git target   : threshold_input/*.csv + metadata.json only")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Export a GitHub-safe, threshold-optimization-only Swing dataset"
    )
    p.add_argument(
        "--range-file",
        help=(
            "range_all_results.csv path or its range folder. "
            "If omitted, the latest modified Swing range is used."
        ),
    )
    p.add_argument("--out", help="Output directory. Default: <range-folder>/threshold_input")
    p.add_argument(
        "--min-score",
        type=float,
        default=45.0,
        help="Lowest score retained for structurally valid rejected rows (default: 45)",
    )
    p.add_argument("--chunksize", type=int, default=100_000)
    p.add_argument(
        "--rows-per-file",
        type=int,
        default=50_000,
        help="Rows per CSV shard. Kept conservative for GitHub's 100 MB/file limit.",
    )
    p.add_argument(
        "--max-file-mb",
        type=float,
        default=80.0,
        help="Hard safety limit per generated shard (default: 80 MB)",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    source = _resolve_source(args.range_file)
    out_dir = Path(args.out) if args.out else source.parent / "threshold_input"
    if not out_dir.is_absolute():
        out_dir = BASE_DIR / out_dir

    export_dataset(
        source,
        out_dir,
        min_score=args.min_score,
        chunksize=args.chunksize,
        rows_per_file=args.rows_per_file,
        max_file_mb=args.max_file_mb,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
