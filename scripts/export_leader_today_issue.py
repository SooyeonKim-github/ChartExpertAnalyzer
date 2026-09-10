from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LEADER_RESULTS = ROOT / "LeaderStockAnalyzer" / "results"
OUTPUT_DIR = ROOT / "results" / "leader"
TODAY = datetime.now().strftime("%Y%m%d")
DATE_RE = re.compile(r"^\d{8}$")


def _latest_result_dir() -> tuple[str, Path] | tuple[None, None]:
    if not LEADER_RESULTS.exists():
        return None, None
    candidates: list[tuple[str, Path]] = []
    for path in LEADER_RESULTS.iterdir():
        if not path.is_dir() or not DATE_RE.fullmatch(path.name):
            continue
        if path.name > TODAY:
            continue
        source = path / "confirmed_candidates.csv"
        if source.exists():
            candidates.append((path.name, source))
    return max(candidates, key=lambda item: item[0]) if candidates else (None, None)


def main() -> int:
    target_date, source = _latest_result_dir()
    if not target_date or source is None:
        print("[WARN] Leader confirmed_candidates.csv not found. today_issue export skipped.")
        return 0

    df = pd.read_csv(source, dtype={"ticker": str}, encoding="utf-8-sig")
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].fillna("").astype(str).str.strip().str.zfill(6)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"today_issue_{target_date}.csv"
    df.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"[INFO] Leader issue date: {target_date}")
    print(f"[DONE] Leader today issue: {len(df)} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
