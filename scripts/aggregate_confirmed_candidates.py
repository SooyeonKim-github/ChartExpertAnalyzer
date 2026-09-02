from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "results"
OUTPUT_FILE = OUTPUT_DIR / "confirmed_candidates.csv"
TODAY = datetime.now().strftime("%Y%m%d")
HORIZONS = (1, 5, 10, 20, 40, 60)

BASE_COLUMNS = [
    "scan_date", "analyzer", "ticker", "name", "status", "score", "timing_score",
    "market", "signal", "pattern_type", "entry_price", "source_file",
]
RETURN_COLUMNS = [
    "return_entry_date", "return_entry_price_d1_open", "latest_price_date", "latest_close",
    "current_return_pct",
    *[f"D+{h}_close_return_pct" for h in HORIZONS],
    "return_updated_at",
]
OUTPUT_COLUMNS = BASE_COLUMNS + RETURN_COLUMNS


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _latest_date_dir(base: Path) -> Path | None:
    today_dir = base / TODAY
    if today_dir.is_dir():
        return today_dir
    if not base.exists():
        return None
    dated = sorted(
        (p for p in base.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 8),
        key=lambda p: p.name,
        reverse=True,
    )
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


def _date_key(value: str | None) -> str:
    text = _clean(value)
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y%m%d")


def _normalized_row(*, scan_date: str, analyzer: str, ticker: str, name: str, status: str,
                    score: str = "", timing_score: str = "", market: str = "",
                    signal: str = "", pattern_type: str = "", entry_price: str = "",
                    source_file: Path) -> dict[str, str]:
    row = {col: "" for col in OUTPUT_COLUMNS}
    row.update({
        "scan_date": _date_key(scan_date),
        "analyzer": analyzer,
        "ticker": _ticker(ticker),
        "name": _clean(name),
        "status": _clean(status),
        "score": _clean(score),
        "timing_score": _clean(timing_score),
        "market": _clean(market),
        "signal": _clean(signal),
        "pattern_type": _clean(pattern_type),
        "entry_price": _clean(entry_price),
        "source_file": str(source_file.relative_to(ROOT)),
    })
    return row


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
            score=r.get("Score", ""), timing_score=r.get("Timing_Score", ""),
            market=r.get("Market", ""), signal=r.get("Primary_Signal", ""),
            entry_price=r.get("Close", ""), source_file=path,
        ))
    return rows


def _normalize_existing(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for old in rows:
        row = {col: _clean(old.get(col, "")) for col in OUTPUT_COLUMNS}
        row["scan_date"] = _date_key(old.get("scan_date"))
        row["ticker"] = _ticker(old.get("ticker"))
        normalized.append(row)
    return normalized


def _merge_history(existing: list[dict[str, str]], current: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    merged: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in existing:
        if not row["scan_date"] or not row["analyzer"] or not row["ticker"]:
            continue
        merged[(row["scan_date"], row["analyzer"], row["ticker"])] = row

    added = 0
    for row in current:
        key = (row["scan_date"], row["analyzer"], row["ticker"])
        if not all(key):
            continue
        old = merged.get(key)
        if old is None:
            merged[key] = row
            added += 1
            continue
        for col in BASE_COLUMNS:
            if row.get(col, "") != "":
                old[col] = row[col]
    return list(merged.values()), added


def _prepare_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    rename = {
        "시가": "Open", "고가": "High", "저가": "Low", "종가": "Close", "거래량": "Volume",
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
    }
    out = out.rename(columns={c: rename.get(str(c), str(c)) for c in out.columns})
    if "Open" not in out.columns or "Close" not in out.columns:
        return pd.DataFrame()
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    out["Open"] = pd.to_numeric(out["Open"], errors="coerce")
    out["Close"] = pd.to_numeric(out["Close"], errors="coerce")
    return out.dropna(subset=["Open", "Close"])


def _fetch_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = _prepare_ohlcv(stock.get_market_ohlcv_by_date(start, end, ticker))
    except Exception as exc:
        print(f"[WARN] Stock OHLCV failed {ticker}: {exc}")
        df = pd.DataFrame()
    if not df.empty:
        return df

    try:
        return _prepare_ohlcv(stock.get_etf_ohlcv_by_date(start, end, ticker))
    except Exception as exc:
        print(f"[WARN] ETF OHLCV failed {ticker}: {exc}")
        return pd.DataFrame()


def _pct(close: float, entry: float) -> str:
    if entry <= 0:
        return ""
    return f"{(close / entry - 1.0) * 100.0:.6f}"


def _update_returns(rows: list[dict[str, str]]) -> None:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("ticker") and len(row.get("scan_date", "")) == 8:
            grouped.setdefault(row["ticker"], []).append(row)

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(grouped)
    for i, (ticker, ticker_rows) in enumerate(sorted(grouped.items()), 1):
        earliest = min(r["scan_date"] for r in ticker_rows)
        print(f"[RETURN] {i}/{total} {ticker} {earliest}~{TODAY}")
        df = _fetch_ohlcv(ticker, earliest, TODAY)
        if df.empty:
            continue

        for row in ticker_rows:
            signal_date = pd.to_datetime(row["scan_date"], format="%Y%m%d", errors="coerce")
            if pd.isna(signal_date):
                continue
            future = df.loc[df.index > signal_date]
            if future.empty:
                row["return_updated_at"] = updated_at
                continue

            entry_date = future.index[0]
            entry_open = float(future.iloc[0]["Open"])
            if entry_open <= 0:
                continue

            row["return_entry_date"] = entry_date.strftime("%Y%m%d")
            row["return_entry_price_d1_open"] = f"{entry_open:.6f}".rstrip("0").rstrip(".")
            row["latest_price_date"] = future.index[-1].strftime("%Y%m%d")
            latest_close = float(future.iloc[-1]["Close"])
            row["latest_close"] = f"{latest_close:.6f}".rstrip("0").rstrip(".")
            row["current_return_pct"] = _pct(latest_close, entry_open)

            for h in HORIZONS:
                col = f"D+{h}_close_return_pct"
                row[col] = _pct(float(future.iloc[h - 1]["Close"]), entry_open) if len(future) >= h else ""
            row["return_updated_at"] = updated_at

        time.sleep(0.05)


def _sort_key(row: dict[str, str]):
    return (
        row.get("scan_date", ""),
        row.get("analyzer", ""),
        -_float(row.get("score")),
        row.get("ticker", ""),
    )


def main() -> int:
    current = _load_kjb() + _load_swing() + _load_ma() + _load_dynamic()

    best_current: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in current:
        key = (row["scan_date"], row["analyzer"], row["ticker"])
        old = best_current.get(key)
        if old is None or (
            _float(row.get("score")), _float(row.get("timing_score"))
        ) > (
            _float(old.get("score")), _float(old.get("timing_score"))
        ):
            best_current[key] = row
    current = list(best_current.values())

    existing = _normalize_existing(_read_csv(OUTPUT_FILE))
    rows, added = _merge_history(existing, current)

    print(f"[INFO] Existing history: {len(existing)}")
    print(f"[INFO] New confirmed rows: {added}")
    print(f"[INFO] Total history rows: {len(rows)}")
    _update_returns(rows)

    rows = sorted(rows, key=_sort_key, reverse=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in current:
        counts[row["analyzer"]] = counts.get(row["analyzer"], 0) + 1

    print(f"[DONE] Confirmed history + returns: {len(rows)} -> {OUTPUT_FILE}")
    for analyzer in ("KJB", "SWING", "MA", "DYNAMIC"):
        print(f"[INFO] Today {analyzer}: {counts.get(analyzer, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
