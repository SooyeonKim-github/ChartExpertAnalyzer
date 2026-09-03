from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
SOURCE_FILE = RESULTS_DIR / "confirmed_candidates.csv"
OUTPUT_FILE = RESULTS_DIR / "today_confiremd_candidates.csv"
TODAY = datetime.now().strftime("%Y%m%d")


def _date_key(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y%m%d")


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_FILE.exists():
        print(f"[ERROR] Confirmed history file not found: {SOURCE_FILE}")
        return 1

    with SOURCE_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [row for row in reader if _date_key(row.get("scan_date")) == TODAY]

    if not fieldnames:
        print(f"[ERROR] Confirmed history has no columns: {SOURCE_FILE}")
        return 1

    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[DONE] Today confirmed candidates: {len(rows)} -> {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
