from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MILESTONES = (5, 10, 20, 60)
COLUMNS = [
    "scan_date",
    "analyzer",
    "ticker",
    "name",
    "status",
    "score",
    "timing_score",
    "market",
    "signal",
    "entry_price",
    "D+5_Pct",
    "D+10_Pct",
    "D+20_Pct",
    "D+60_Pct",
    "source_file",
]


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        print(f"[WARN] Missing: {path}")
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _clean(value) -> str:
    text = str(value or "").strip()
    return "" if text.lower() == "nan" else text


def _ticker(value) -> str:
    text = _clean(value).upper()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _float(value) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return float("-inf")


def _pct(value, multiplier: float = 1.0) -> str:
    text = _clean(value)
    if not text:
        return ""
    try:
        number = float(text.replace(",", ""))
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number * multiplier:.10g}"


def _latest_date_dir(base: Path) -> Path | None:
    if not base.exists():
        return None
    dirs = sorted(
        [p for p in base.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 8],
        key=lambda p: p.name,
        reverse=True,
    )
    return dirs[0] if dirs else None


def _row(
    analyzer: str,
    source: Path,
    raw: dict[str, str],
    *,
    date_key: str,
    ticker_key: str,
    name_key: str,
    status_key: str,
    score_key: str,
    timing_key: str = "",
    signal_key: str = "",
    entry_key: str = "",
) -> dict[str, str]:
    row = {
        "scan_date": _clean(raw.get(date_key, "")),
        "analyzer": analyzer,
        "ticker": _ticker(raw.get(ticker_key, "")),
        "name": _clean(raw.get(name_key, "")),
        "status": _clean(raw.get(status_key, "")).upper(),
        "score": _clean(raw.get(score_key, "")) if score_key else "",
        "timing_score": _clean(raw.get(timing_key, "")) if timing_key else "",
        "market": "US",
        "signal": _clean(raw.get(signal_key, "")) if signal_key else "",
        "entry_price": _clean(raw.get(entry_key, "")) if entry_key else "",
        "source_file": str(source.relative_to(ROOT)),
    }
    for h in MILESTONES:
        row[f"D+{h}_Pct"] = ""
    return row


def _screen_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    kjb = ROOT / "KJBChartAnalyzer" / "output_us" / "top300_screen.csv"
    for raw in _read(kjb):
        if _clean(raw.get("Status")).upper() != "CONFIRMED":
            continue
        rows.append(
            _row(
                "KJB", kjb, raw,
                date_key="asof", ticker_key="ticker", name_key="name",
                status_key="Status", score_key="score", timing_key="timing_score",
                signal_key="action", entry_key="close",
            )
        )

    swing_dir = _latest_date_dir(ROOT / "SwingChartProbabilityAnalyzer" / "results_us")
    if swing_dir:
        swing = swing_dir / "scan_results.csv"
        for raw in _read(swing):
            if _clean(raw.get("Status")).upper() not in {"STRONG_CONFIRMED", "CONFIRMED"}:
                continue
            rows.append(
                _row(
                    "SWING", swing, raw,
                    date_key="Actual_Date", ticker_key="Ticker", name_key="Name",
                    status_key="Status", score_key="Score", signal_key="Primary_Signal",
                    entry_key="Close",
                )
            )

    ma_dir = _latest_date_dir(ROOT / "MAChartAnalyzer" / "results_us")
    if ma_dir:
        ma = ma_dir / "scan_results.csv"
        for raw in _read(ma):
            if _clean(raw.get("Status")).upper() not in {"STRONG_CONFIRMED", "CONFIRMED"}:
                continue
            rows.append(
                _row(
                    "MA", ma, raw,
                    date_key="Actual_Date", ticker_key="Ticker", name_key="Name",
                    status_key="Status", score_key="Score", timing_key="Timing_Score",
                    signal_key="Primary_Signal", entry_key="Close",
                )
            )

    dynamic_dir = _latest_date_dir(ROOT / "DynamicChartAnalyzer" / "results_us")
    if dynamic_dir:
        dynamic = dynamic_dir / "scan_results.csv"
        for raw in _read(dynamic):
            if _clean(raw.get("Status")).upper() != "CONFIRMED":
                continue
            rows.append(
                _row(
                    "DYNAMIC", dynamic, raw,
                    date_key="Actual_Date", ticker_key="Ticker", name_key="Name",
                    status_key="Status", score_key="", signal_key="Primary_Signal",
                    entry_key="Close",
                )
            )
    return rows


def _range_rows(date_range: str) -> list[dict[str, str]]:
    start, end = date_range.replace("～", "~").split("~", 1)
    key = f"range_{start}_{end}"
    specs = [
        (
            "KJB",
            ROOT / "KJBChartAnalyzer" / "results_us" / key / "chart_range_events.csv",
            "signal_date", "ticker", "name", "Status", "selection_score", "timing_score", "entry_status", "entry_close",
        ),
        (
            "SWING",
            ROOT / "SwingChartProbabilityAnalyzer" / "results_us" / key / "range_candidates.csv",
            "Actual_Date", "Ticker", "Name", "Status", "Score", "", "Primary_Signal", "Close",
        ),
        (
            "MA",
            ROOT / "MAChartAnalyzer" / "results_us" / key / "range_candidates.csv",
            "Actual_Date", "Ticker", "Name", "Status", "Score", "Timing_Score", "Primary_Signal", "Close",
        ),
        (
            "DYNAMIC",
            ROOT / "DynamicChartAnalyzer" / "results_us" / key / "range_candidates.csv",
            "Actual_Date", "Ticker", "Name", "Status", "", "", "Primary_Signal", "Close",
        ),
    ]
    rows: list[dict[str, str]] = []
    for analyzer, path, dk, tk, nk, sk, sc, tim, sig, entry in specs:
        for raw in _read(path):
            status = _clean(raw.get(sk)).upper()
            if status not in {"STRONG_CONFIRMED", "CONFIRMED"}:
                continue
            row = _row(
                analyzer, path, raw,
                date_key=dk, ticker_key=tk, name_key=nk, status_key=sk,
                score_key=sc, timing_key=tim, signal_key=sig, entry_key=entry,
            )
            for h in MILESTONES:
                if analyzer in {"KJB", "DYNAMIC"}:
                    # KJB/Dynamic store forward returns as decimal fractions.
                    row[f"D+{h}_Pct"] = _pct(raw.get(f"D+{h}", ""), 100.0)
                else:
                    # Swing/MA already store forward returns in percentage points.
                    row[f"D+{h}_Pct"] = _pct(raw.get(f"D+{h}_Close_Return_Pct", ""))
            rows.append(row)
    return rows


def _dedupe(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    best: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["scan_date"], row["analyzer"], row["ticker"])
        old = best.get(key)
        if old is None or (_float(row["score"]), _float(row["timing_score"])) > (
            _float(old["score"]), _float(old["timing_score"])
        ):
            best[key] = row
    return list(best.values())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aggregate confirmed US analyzer candidates.")
    p.add_argument("--mode", choices=["screen", "range"], required=True)
    p.add_argument("--date-range", default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "range" and "~" not in args.date_range and "～" not in args.date_range:
        raise ValueError("--date-range YYYYMMDD~YYYYMMDD is required for range mode")

    rows = _screen_rows() if args.mode == "screen" else _range_rows(args.date_range)
    rows = sorted(
        _dedupe(rows),
        key=lambda r: (
            r["scan_date"],
            0 if r["status"] == "STRONG_CONFIRMED" else 1,
            r["analyzer"],
            -_float(r["score"]),
            r["ticker"],
        ),
    )

    if args.mode == "screen":
        out = ROOT / "results_us" / "confirmed_candidates.csv"
    else:
        start, end = args.date_range.replace("～", "~").split("~", 1)
        out = ROOT / "results_us" / f"range_{start}_{end}" / "confirmed_candidates.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    counts = {}
    for row in rows:
        counts[row["analyzer"]] = counts.get(row["analyzer"], 0) + 1
    print(f"[DONE] US confirmed candidates: {len(rows)} -> {out}")
    for analyzer in ("KJB", "SWING", "MA", "DYNAMIC"):
        print(f"[INFO] {analyzer}: {counts.get(analyzer, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
