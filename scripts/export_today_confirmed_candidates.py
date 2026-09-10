from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from MarketData import get_market_data_service, to_upper_ohlcv  # noqa: E402

RESULTS_DIR = ROOT / "results"
SOURCE_FILE = RESULTS_DIR / "confirmed_candidates.csv"
TODAY = datetime.now().strftime("%Y%m%d")
TECHNICAL_LOOKBACK_CALENDAR_DAYS = 400

TECHNICAL_COLUMNS = [
    "technical_price_date",
    "technical_close",
    "volume",
    "volume_ma20",
    "volume_ratio_20d",
    "ma5",
    "ma20",
    "ma60",
    "ma120",
    "rsi14",
    "macd",
    "macd_signal",
    "macd_hist",
    "recent_high_20d",
    "recent_high_20d_date",
    "recent_low_20d",
    "recent_low_20d_date",
    "distance_from_high_20d_pct",
    "distance_from_low_20d_pct",
]


def _clean(value: str | None) -> str:
    text = str(value or "").strip()
    return "" if text.lower() == "nan" else text


def _ticker(value: str | None) -> str:
    text = _clean(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text else ""


def _date_key(value: str | None) -> str:
    text = _clean(value)
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


def _number(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _prepare_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = to_upper_ohlcv(df)
    for col in ("High", "Low", "Close", "Volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()]
    return out.dropna(subset=["High", "Low", "Close"]).sort_index()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.mask(avg_loss == 0.0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.mask((avg_loss == 0.0) & (avg_gain > 0.0), 100.0)
    return rsi.mask((avg_loss == 0.0) & (avg_gain == 0.0), 50.0)


def _technical_snapshot(df: pd.DataFrame, target_date: str) -> dict[str, str]:
    result = {col: "" for col in TECHNICAL_COLUMNS}
    if df.empty:
        return result

    target_ts = pd.to_datetime(target_date, format="%Y%m%d", errors="coerce")
    if pd.isna(target_ts):
        return result

    hist = df.loc[df.index.normalize() <= target_ts.normalize()].copy()
    if hist.empty:
        return result

    close = hist["Close"].astype(float)
    volume = hist["Volume"].astype(float).fillna(0.0)

    for window in (5, 20, 60, 120):
        hist[f"MA{window}"] = close.rolling(window=window, min_periods=window).mean()

    hist["Volume_MA20"] = volume.rolling(window=20, min_periods=20).mean()
    hist["RSI14"] = _rsi(close, 14)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    hist["MACD"] = ema12 - ema26
    hist["MACD_Signal"] = hist["MACD"].ewm(span=9, adjust=False).mean()
    hist["MACD_Hist"] = hist["MACD"] - hist["MACD_Signal"]

    latest = hist.iloc[-1]
    latest_date = pd.Timestamp(hist.index[-1])
    latest_close = float(latest["Close"])
    latest_volume = float(latest["Volume"]) if not pd.isna(latest["Volume"]) else 0.0
    volume_ma20 = latest["Volume_MA20"]

    result.update(
        {
            "technical_price_date": latest_date.strftime("%Y%m%d"),
            "technical_close": _number(latest_close),
            "volume": str(int(round(latest_volume))),
            "volume_ma20": _number(volume_ma20),
            "volume_ratio_20d": (
                _number(latest_volume / float(volume_ma20))
                if pd.notna(volume_ma20) and float(volume_ma20) > 0
                else ""
            ),
            "ma5": _number(latest["MA5"]),
            "ma20": _number(latest["MA20"]),
            "ma60": _number(latest["MA60"]),
            "ma120": _number(latest["MA120"]),
            "rsi14": _number(latest["RSI14"]),
            "macd": _number(latest["MACD"]),
            "macd_signal": _number(latest["MACD_Signal"]),
            "macd_hist": _number(latest["MACD_Hist"]),
        }
    )

    recent = hist.tail(20)
    if len(recent) >= 20:
        high_idx = recent["High"].idxmax()
        low_idx = recent["Low"].idxmin()
        recent_high = float(recent.loc[high_idx, "High"])
        recent_low = float(recent.loc[low_idx, "Low"])
        result.update(
            {
                "recent_high_20d": _number(recent_high),
                "recent_high_20d_date": pd.Timestamp(high_idx).strftime("%Y%m%d"),
                "recent_low_20d": _number(recent_low),
                "recent_low_20d_date": pd.Timestamp(low_idx).strftime("%Y%m%d"),
                "distance_from_high_20d_pct": (
                    _number((latest_close / recent_high - 1.0) * 100.0)
                    if recent_high > 0
                    else ""
                ),
                "distance_from_low_20d_pct": (
                    _number((latest_close / recent_low - 1.0) * 100.0)
                    if recent_low > 0
                    else ""
                ),
            }
        )

    return result


def _fetch_technical_snapshot(ticker: str, market: str, target_date: str) -> dict[str, str]:
    target_ts = pd.to_datetime(target_date, format="%Y%m%d", errors="coerce")
    if pd.isna(target_ts):
        return {col: "" for col in TECHNICAL_COLUMNS}

    start = (target_ts - pd.Timedelta(days=TECHNICAL_LOOKBACK_CALENDAR_DAYS)).strftime("%Y%m%d")
    try:
        raw = get_market_data_service().get_ohlcv(
            ticker,
            start,
            target_date,
            market_hint=market or None,
            allow_etf=False,
            fallback_yfinance=True,
        )
        return _technical_snapshot(_prepare_ohlcv(raw), target_date)
    except Exception as exc:
        print(f"[WARN] Technical data failed {ticker}: {exc}")
        return {col: "" for col in TECHNICAL_COLUMNS}


def _enrich_rows(rows: list[dict[str, str]], target_date: str) -> list[dict[str, str]]:
    snapshot_cache: dict[tuple[str, str], dict[str, str]] = {}
    total = len(rows)
    for i, row in enumerate(rows, 1):
        ticker = _ticker(row.get("ticker"))
        market = _clean(row.get("market")).upper()
        row["ticker"] = ticker
        cache_key = (ticker, market)
        if cache_key not in snapshot_cache:
            print(f"[TECH] {i}/{total} {ticker} target={target_date}")
            snapshot_cache[cache_key] = _fetch_technical_snapshot(ticker, market, target_date)
        row.update(snapshot_cache[cache_key])
    return rows


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_FILE.exists():
        print(f"[ERROR] Confirmed history file not found: {SOURCE_FILE}")
        return 1

    with SOURCE_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        source_fieldnames = list(reader.fieldnames or [])
        all_rows = list(reader)

    if not source_fieldnames:
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
    rows = _enrich_rows(rows, target_date)

    fieldnames = source_fieldnames + [
        col for col in TECHNICAL_COLUMNS if col not in source_fieldnames
    ]
    output_file = RESULTS_DIR / f"today_confirmed_{target_date}.csv"

    with output_file.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[INFO] Export target scan_date: {target_date}")
    print(f"[DONE] Latest confirmed candidates: {len(rows)} -> {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
