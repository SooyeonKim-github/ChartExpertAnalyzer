from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "MaterialAnalyzer" / "data" / "ticker_link_report.csv"
OUTPUT_DIR = ROOT / "results" / "material"
TODAY = datetime.now().strftime("%Y%m%d")
KEEP_STATUSES = {"STRONG", "CONFIRMED", "WATCH"}


def _date_key(value) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if len(text) == 8 and text.isdigit():
        parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    else:
        parsed = pd.to_datetime(text, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y%m%d")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"today_issue_{TODAY}.csv"

    if not SOURCE.exists():
        print(f"[WARN] Material ticker link report not found: {SOURCE}")
        pd.DataFrame().to_csv(output, index=False, encoding="utf-8-sig")
        print(f"[DONE] Material today issue: 0 -> {output}")
        return 0

    df = pd.read_csv(SOURCE, dtype={"ticker": str, "market_date": str}, encoding="utf-8-sig")
    if "market_date" not in df.columns:
        print("[WARN] Material ticker link report has no market_date column.")
        df.head(0).to_csv(output, index=False, encoding="utf-8-sig")
        print(f"[DONE] Material today issue: 0 -> {output}")
        return 0

    df["_issue_date"] = df["market_date"].map(_date_key)
    valid_dates = sorted({d for d in df["_issue_date"] if d}, reverse=True)
    latest_linked_date = valid_dates[0] if valid_dates else ""

    if latest_linked_date and latest_linked_date < TODAY:
        print(
            f"[WARN] Latest linked material date is stale: {latest_linked_date} "
            f"(today={TODAY}). No fallback to stale date will be used."
        )
    elif not latest_linked_date:
        print("[WARN] Material ticker link report has no valid market_date values.")

    out = df[df["_issue_date"] == TODAY].copy()
    before_status_filter = len(out)

    if "material_status" in out.columns:
        status = out["material_status"].fillna("").astype(str).str.upper().str.strip()
        out = out[status.isin(KEEP_STATUSES)].copy()

    if "ticker" in out.columns:
        out["ticker"] = out["ticker"].fillna("").astype(str).str.strip().str.zfill(6)

    out.drop(columns=["_issue_date"], inplace=True, errors="ignore")

    # Preserve the report schema even when there are no qualifying rows today.
    if out.empty:
        columns = [c for c in df.columns if c != "_issue_date"]
        out = pd.DataFrame(columns=columns)

    out.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"[INFO] Material issue date: {TODAY}")
    print(f"[INFO] Latest linked material date in report: {latest_linked_date or 'NONE'}")
    print(f"[INFO] Rows dated today before status filter: {before_status_filter}")
    print(f"[INFO] Included statuses: {', '.join(sorted(KEEP_STATUSES))}")
    print(f"[DONE] Material today issue: {len(out)} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
