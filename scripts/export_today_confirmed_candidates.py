from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
SOURCE_FILE = RESULTS_DIR / "confirmed_candidates.csv"
OUTPUT_FILE = RESULTS_DIR / "today_confirmed_candidates.csv"
TODAY = datetime.now().strftime("%Y%m%d")


def _date_key(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y%m%d")


def _latest_scan_date(rows: list[dict[str, str]]) -> str:
    dates = sorted(
        {
            date_key
            for row in rows
            if (date_key := _date_key(row.get("scan_date"))) and date_key <= TODAY
        },
        reverse=True,
    )
    if dates:
        return dates[0]

    # Defensive fallback for malformed/future-dated history rows.
    all_dates = sorted(
        {
            date_key
            for row in rows
            if (date_key := _date_key(row.get("scan_date")))
        },
        reverse=True,
    )
    return all_dates[0] if all_dates else ""


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_FILE.exists():
        print(f"[ERROR] Confirmed history file not found: {SOURCE_FILE}")
        return 1

    with SOURCE_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        all_rows = list(reader)

    if not fieldnames:
        print(f"[ERROR] Confirmed history has no columns: {SOURCE_FILE}")
        return 1

    target_date = _latest_scan_date(all_rows)
    if not target_date:
        print(f"[ERROR] Confirmed history has no valid scan_date: {SOURCE_FILE}")
        return 1

    rows = [
        row
        for row in all_rows
        if _date_key(row.get("scan_date")) == target_date
    ]

    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[INFO] Export target scan_date: {target_date}")
    print(f"[DONE] Latest confirmed candidates: {len(rows)} -> {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
