from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "reference" / "ticker_master_krx.csv"
FIELDS = ["ticker", "name", "aliases", "market", "sector", "industry", "enabled"]
MIN_EXPECTED_ROWS = 1000


def _meta_path(path: Path) -> Path:
    return path.with_name(path.stem + ".refresh.json")


def _read_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        return {str(row.get("ticker", "")).strip().zfill(6): row for row in csv.DictReader(fp) if row.get("ticker")}


def _is_fresh(path: Path, stale_days: int) -> bool:
    if stale_days <= 0:
        return False
    meta = _meta_path(path)
    if not path.exists() or not meta.exists():
        return False
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
        built_at = datetime.fromisoformat(str(payload.get("built_at", "")))
        if built_at.tzinfo is None:
            built_at = built_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - built_at.astimezone(timezone.utc)
        return age.total_seconds() < stale_days * 86400
    except Exception:
        return False


def _latest_market_snapshot(stock_module):
    try:
        kospi = list(stock_module.get_market_ticker_list(market="KOSPI"))
        kosdaq = list(stock_module.get_market_ticker_list(market="KOSDAQ"))
        if kospi or kosdaq:
            return "LATEST", (("KOSPI", kospi), ("KOSDAQ", kosdaq))
    except Exception:
        pass
    for offset in range(0, 31):
        target = (date.today() - timedelta(days=offset)).strftime("%Y%m%d")
        try:
            kospi = list(stock_module.get_market_ticker_list(target, market="KOSPI"))
            kosdaq = list(stock_module.get_market_ticker_list(target, market="KOSDAQ"))
        except Exception:
            continue
        if kospi or kosdaq:
            return target, (("KOSPI", kospi), ("KOSDAQ", kosdaq))
    raise RuntimeError("empty latest-business-day and 31-day KRX ticker queries")


def _rows_from_pykrx(stock_module, existing):
    snapshot_date, markets = _latest_market_snapshot(stock_module)
    rows = []
    seen = set()
    for market, tickers in markets:
        for raw_ticker in tickers:
            ticker = str(raw_ticker).zfill(6)
            if ticker in seen:
                continue
            seen.add(ticker)
            name = str(stock_module.get_market_ticker_name(ticker) or "").strip()
            if not name:
                continue
            old = existing.get(ticker, {})
            aliases = [x for x in str(old.get("aliases", "")).split("|") if x]
            old_name = str(old.get("name", "")).strip()
            if old_name and old_name != name and old_name not in aliases:
                aliases.append(old_name)
            rows.append({
                "ticker": ticker,
                "name": name,
                "aliases": "|".join(aliases),
                "market": market,
                "sector": str(old.get("sector", "")).strip(),
                "industry": str(old.get("industry", "")).strip(),
                "enabled": "1",
            })
    return snapshot_date, rows


def _provider_shared_marketdata(existing):
    from MarketData.service import load_pykrx_stock
    stock = load_pykrx_stock()
    return _rows_from_pykrx(stock, existing)


def _provider_finance_data_reader(existing):
    import FinanceDataReader as fdr
    frame = fdr.StockListing("KRX")
    if frame is None or frame.empty:
        raise RuntimeError("FinanceDataReader StockListing('KRX') returned empty")
    rows = []
    seen = set()
    for _, row in frame.iterrows():
        ticker = str(row.get("Code", row.get("Symbol", ""))).strip().zfill(6)
        name = str(row.get("Name", "")).strip()
        market = str(row.get("Market", row.get("MarketId", ""))).strip().upper()
        if market not in {"KOSPI", "KOSDAQ"} or not ticker.isdigit() or len(ticker) != 6 or not name:
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        old = existing.get(ticker, {})
        aliases = [x for x in str(old.get("aliases", "")).split("|") if x]
        old_name = str(old.get("name", "")).strip()
        if old_name and old_name != name and old_name not in aliases:
            aliases.append(old_name)
        rows.append({
            "ticker": ticker,
            "name": name,
            "aliases": "|".join(aliases),
            "market": market,
            "sector": str(old.get("sector", "")).strip(),
            "industry": str(old.get("industry", "")).strip(),
            "enabled": "1",
        })
    return "FDR_LATEST", rows


def _provider_direct_pykrx(existing):
    from pykrx import stock
    return _rows_from_pykrx(stock, existing)


def _choose_provider(existing):
    providers = (
        ("MARKETDATA_SHARED_PYKRX", _provider_shared_marketdata),
        ("FINANCE_DATA_READER", _provider_finance_data_reader),
        ("DIRECT_PYKRX", _provider_direct_pykrx),
    )
    errors = []
    for name, provider in providers:
        try:
            snapshot_date, rows = provider(existing)
            if len(rows) < MIN_EXPECTED_ROWS:
                raise RuntimeError(f"provider returned only {len(rows)} rows")
            print(f"[OK] ticker master provider={name} rows={len(rows)}")
            return name, snapshot_date, rows
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"[WARN] ticker master provider failed: {errors[-1]}")
    raise RuntimeError("all ticker-master providers failed | " + " | ".join(errors))


def build(output: Path = DEFAULT_OUTPUT, *, if_stale_days: int = 0, best_effort: bool = False) -> int:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if _is_fresh(output, if_stale_days):
        print(f"[SKIP] ticker master refresh is fresh: {_meta_path(output)}")
        return 0

    try:
        existing = _read_existing(output)
        provider, snapshot_date, rows = _choose_provider(existing)
        rows.sort(key=lambda row: (row["market"], row["ticker"]))
        tmp = output.with_suffix(output.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(output)
        _meta_path(output).write_text(json.dumps({
            "built_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_date": snapshot_date,
            "provider": provider,
            "count": len(rows),
            "markets": ["KOSPI", "KOSDAQ"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] ticker master {snapshot_date}: {len(rows)} tickers -> {output}")
        return len(rows)
    except Exception as exc:
        if best_effort:
            print(f"[WARN] ticker master refresh skipped: {type(exc).__name__}: {exc}")
            if output.exists():
                print(f"[WARN] using existing generated master: {output}")
            else:
                print("[WARN] generated master unavailable; manual seed + EventExtractor bootstrap will be used")
            return 0
        raise


def main():
    parser = argparse.ArgumentParser(description="Build KOSPI/KOSDAQ ticker_master_krx.csv with provider fallbacks")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--if-stale-days", type=int, default=0)
    parser.add_argument("--best-effort", action="store_true")
    args = parser.parse_args()
    build(Path(args.output), if_stale_days=args.if_stale_days, best_effort=args.best_effort)


if __name__ == "__main__":
    main()
