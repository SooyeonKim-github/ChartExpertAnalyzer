from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "MaterialAnalyzer" / "data" / "ticker_link_report.csv"
OUTPUT_DIR = ROOT / "results" / "material"
TODAY_DT = datetime.now().date()
TODAY = TODAY_DT.strftime("%Y%m%d")
WINDOW_START = (TODAY_DT - timedelta(days=4)).strftime("%Y%m%d")
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

    # Keep the latest five calendar days including today.
    # Example on 2026-09-11: 20260907 ~ 20260911.
    out = df[(df["_issue_date"] >= WINDOW_START) & (df["_issue_date"] <= TODAY)].copy()
    before_status_filter = len(out)

    if "material_status" in out.columns:
        status = out["material_status"].fillna("").astype(str).str.upper().str.strip()
        out = out[status.isin(KEEP_STATUSES)].copy()

    if "ticker" in out.columns:
        out["ticker"] = out["ticker"].fillna("").astype(str).str.strip().str.zfill(6)

    out.drop(columns=["_issue_date"], inplace=True, errors="ignore")

    sort_cols = [c for c in ["market_date", "ticker_material_score", "material_score"] if c in out.columns]
    if sort_cols:
        ascending = [False] * len(sort_cols)
        out = out.sort_values(sort_cols, ascending=ascending, na_position="last")

    # Preserve the report schema even when there are no qualifying rows in the five-day window.
    if out.empty:
        columns = [c for c in df.columns if c != "_issue_date"]
        out = pd.DataFrame(columns=columns)

    out.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"[INFO] Material issue output date : {TODAY}")
    print(f"[INFO] Material collection window : {WINDOW_START} ~ {TODAY} (5 calendar days)")
    print(f"[INFO] Rows in window before status filter: {before_status_filter}")
    print(f"[INFO] Included statuses: {', '.join(sorted(KEEP_STATUSES))}")
    print(f"[DONE] Material today issue: {len(out)} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
