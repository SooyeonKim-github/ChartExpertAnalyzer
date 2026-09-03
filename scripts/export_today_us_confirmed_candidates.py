from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results_us"
SOURCE_FILE = RESULTS_DIR / "confirmed_candidates.csv"
OUTPUT_FILE = RESULTS_DIR / "today_confiremd_candidates.csv"


def _clean(value: str | None) -> str:
    text = str(value or "").strip()
    return "" if text.lower() == "nan" else text


def _date_key(value: str | None) -> str:
    text = _clean(value)
    if not text:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_FILE.exists():
        print(f"[ERROR] US confirmed candidates file not found: {SOURCE_FILE}")
        return 1

    with SOURCE_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if not fieldnames:
        print(f"[ERROR] US confirmed candidates has no columns: {SOURCE_FILE}")
        return 1

    valid_dates = [_date_key(row.get("scan_date")) for row in rows]
    valid_dates = [date for date in valid_dates if date]
    latest_scan_date = max(valid_dates) if valid_dates else ""
    today_rows = [row for row in rows if _date_key(row.get("scan_date")) == latest_scan_date] if latest_scan_date else []

    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(today_rows)

    date_label = latest_scan_date or "N/A"
    print(f"[DONE] Today US confirmed candidates: {len(today_rows)} date={date_label} -> {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
