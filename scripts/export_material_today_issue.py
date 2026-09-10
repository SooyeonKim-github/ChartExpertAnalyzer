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
    if not SOURCE.exists():
        print(f"[WARN] Material ticker link report not found: {SOURCE}")
        return 0

    df = pd.read_csv(SOURCE, dtype={"ticker": str, "market_date": str}, encoding="utf-8-sig")
    if df.empty or "market_date" not in df.columns:
        print("[WARN] Material ticker link report has no rows/market_date. today_issue export skipped.")
        return 0

    df["_issue_date"] = df["market_date"].map(_date_key)
    valid_dates = sorted({d for d in df["_issue_date"] if d and d <= TODAY}, reverse=True)
    if not valid_dates:
        print("[WARN] Material report has no valid market_date for today_issue export.")
        return 0

    target_date = valid_dates[0]
    out = df[df["_issue_date"] == target_date].copy()
    if "material_status" in out.columns:
        status = out["material_status"].fillna("").astype(str).str.upper().str.strip()
        out = out[status.isin(KEEP_STATUSES)].copy()
    if "ticker" in out.columns:
        out["ticker"] = out["ticker"].fillna("").astype(str).str.strip().str.zfill(6)
    out.drop(columns=["_issue_date"], inplace=True, errors="ignore")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"today_issue_{target_date}.csv"
    out.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"[INFO] Material issue date: {target_date}")
    print(f"[INFO] Included statuses: {', '.join(sorted(KEEP_STATUSES))}")
    print(f"[DONE] Material today issue: {len(out)} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
