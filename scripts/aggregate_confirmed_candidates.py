from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "results"
OUTPUT_FILE = OUTPUT_DIR / "confirmed_candidates.csv"
TODAY = datetime.now().strftime("%Y%m%d")

OUTPUT_COLUMNS = [
    "scan_date", "analyzer", "ticker", "name", "status", "score", "timing_score",
    "market", "signal", "pattern_type", "entry_price", "source_file",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        print(f"[WARN] Source file not found: {path}")
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _latest_date_dir(base: Path) -> Path | None:
    today_dir = base / TODAY
    if today_dir.is_dir():
        return today_dir
    if not base.exists():
        return None
    dated = sorted((p for p in base.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 8), key=lambda p: p.name, reverse=True)
    return dated[0] if dated else None


def _ticker(value: str | None) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text else ""


def _float(value: str | None) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return float("-inf")


def _clean(value: str | None) -> str:
    text = str(value or "").strip()
    return "" if text.lower() == "nan" else text


def _normalized_row(*, scan_date: str, analyzer: str, ticker: str, name: str, status: str,
                    score: str = "", timing_score: str = "", market: str = "",
                    signal: str = "", pattern_type: str = "", entry_price: str = "",
                    source_file: Path) -> dict[str, str]:
    return {
        "scan_date": _clean(scan_date), "analyzer": analyzer, "ticker": _ticker(ticker),
        "name": _clean(name), "status": _clean(status), "score": _clean(score),
        "timing_score": _clean(timing_score), "market": _clean(market),
        "signal": _clean(signal), "pattern_type": _clean(pattern_type),
        "entry_price": _clean(entry_price), "source_file": str(source_file.relative_to(ROOT)),
    }


def _load_kjb() -> list[dict[str, str]]:
    path = ROOT / "KJBChartAnalyzer" / "output" / "top100_screen.csv"
    rows = []
    for r in _read_csv(path):
        if _clean(r.get("Status")).upper() != "CONFIRMED":
            continue
        rows.append(_normalized_row(
            scan_date=r.get("asof", ""), analyzer="KJB", ticker=r.get("ticker", ""),
            name=r.get("name", ""), status=r.get("Status", ""), score=r.get("score", ""),
            timing_score=r.get("timing_score", ""), market=r.get("market", ""),
            signal=r.get("action", ""), entry_price=r.get("close", ""), source_file=path,
        ))
    return rows


def _load_swing() -> list[dict[str, str]]:
    result_dir = _latest_date_dir(ROOT / "SwingChartProbabilityAnalyzer" / "results")
    if result_dir is None:
        print("[WARN] Swing result directory not found.")
        return []
    path = result_dir / "scan_results.csv"
    rows = []
    for r in _read_csv(path):
        status = _clean(r.get("Status")).upper()
        if status not in {"STRONG_CONFIRMED", "CONFIRMED"}:
            continue
        rows.append(_normalized_row(
            scan_date=r.get("Actual_Date", result_dir.name), analyzer="SWING",
            ticker=r.get("Ticker", ""), name=r.get("Name", ""), status=status,
            score=r.get("Score", ""), market=r.get("Market", ""),
            signal=r.get("Primary_Signal", ""), entry_price=r.get("Close", ""), source_file=path,
        ))
    return rows


def _load_ma() -> list[dict[str, str]]:
    result_dir = _latest_date_dir(ROOT / "MAChartAnalyzer" / "results")
    if result_dir is None:
        print("[WARN] MA result directory not found.")
        return []
    path = result_dir / "scan_results.csv"
    rows = []
    for r in _read_csv(path):
        status = _clean(r.get("Status")).upper()
        if status not in {"STRONG_CONFIRMED", "CONFIRMED"}:
            continue
        rows.append(_normalized_row(
            scan_date=r.get("Actual_Date", result_dir.name), analyzer="MA",
            ticker=r.get("Ticker", ""), name=r.get("Name", ""), status=status,
            score=r.get("Score", ""), timing_score=r.get("Timing_Score", ""),
            market=r.get("Market", ""), signal=r.get("Primary_Signal", ""),
            entry_price=r.get("Close", ""), source_file=path,
        ))
    return rows


def _load_dynamic() -> list[dict[str, str]]:
    result_dir = _latest_date_dir(ROOT / "DynamicChartAnalyzer" / "results")
    if result_dir is None:
        print("[WARN] Dynamic result directory not found.")
        return []
    path = result_dir / "scan_results.csv"
    rows = []
    for r in _read_csv(path):
        status = _clean(r.get("Status")).upper()
        if status != "CONFIRMED":
            continue
        rows.append(_normalized_row(
            scan_date=r.get("Actual_Date", result_dir.name), analyzer="DYNAMIC",
            ticker=r.get("Ticker", ""), name=r.get("Name", ""), status=status,
            market=r.get("Market", ""), signal=r.get("Primary_Signal", ""),
            entry_price=r.get("Close", ""), source_file=path,
        ))
    return rows


def _dedupe(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    best: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["analyzer"], row["ticker"])
        old = best.get(key)
        if old is None or (_float(row.get("score")), _float(row.get("timing_score"))) > (_float(old.get("score")), _float(old.get("timing_score"))):
            best[key] = row
    return list(best.values())


def _sort_key(row: dict[str, str]):
    status_rank = 0 if row["status"] == "STRONG_CONFIRMED" else 1
    return (status_rank, row["analyzer"], -_float(row.get("score")), row["ticker"])


def main() -> int:
    rows = _load_kjb() + _load_swing() + _load_ma() + _load_dynamic()
    rows = sorted(_dedupe(rows), key=_sort_key)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["analyzer"]] = counts.get(row["analyzer"], 0) + 1
    print(f"[DONE] Confirmed candidates: {len(rows)} -> {OUTPUT_FILE}")
    for analyzer in ("KJB", "SWING", "MA", "DYNAMIC"):
        print(f"[INFO] {analyzer}: {counts.get(analyzer, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
