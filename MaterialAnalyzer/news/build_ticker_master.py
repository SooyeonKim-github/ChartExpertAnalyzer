from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "reference" / "ticker_master.csv"
FIELDS = ["ticker", "name", "aliases", "market", "sector", "industry", "enabled"]


def _read_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        return {str(row.get("ticker", "")).strip().zfill(6): row for row in csv.DictReader(fp) if row.get("ticker")}


def _is_fresh(path: Path, stale_days: int) -> bool:
    if not path.exists() or stale_days <= 0:
        return False
    age_days = (time.time() - path.stat().st_mtime) / 86400.0
    return age_days < stale_days


def _latest_market_snapshot(stock_module):
    for offset in range(0, 15):
        target = (date.today() - timedelta(days=offset)).strftime("%Y%m%d")
        kospi = list(stock_module.get_market_ticker_list(target, market="KOSPI"))
        kosdaq = list(stock_module.get_market_ticker_list(target, market="KOSDAQ"))
        if kospi or kosdaq:
            return target, (("KOSPI", kospi), ("KOSDAQ", kosdaq))
    raise RuntimeError("KRX ticker list was empty for the latest 15 calendar days")


def build(output: Path = DEFAULT_OUTPUT, *, if_stale_days: int = 0, best_effort: bool = False) -> int:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if _is_fresh(output, if_stale_days):
        print(f"[SKIP] ticker master is fresh: {output}")
        return 0

    try:
        from pykrx import stock

        snapshot_date, markets = _latest_market_snapshot(stock)
        existing = _read_existing(output)
        rows: list[dict[str, str]] = []
        seen = set()
        for market, tickers in markets:
            for ticker in tickers:
                ticker = str(ticker).zfill(6)
                if ticker in seen:
                    continue
                seen.add(ticker)
                name = str(stock.get_market_ticker_name(ticker) or "").strip()
                if not name:
                    continue
                old = existing.get(ticker, {})
                aliases = str(old.get("aliases", "")).strip()
                # Preserve any older canonical name as an alias if KRX name changed.
                old_name = str(old.get("name", "")).strip()
                if old_name and old_name != name:
                    alias_values = [x for x in aliases.split("|") if x]
                    if old_name not in alias_values:
                        alias_values.append(old_name)
                    aliases = "|".join(alias_values)
                rows.append({
                    "ticker": ticker,
                    "name": name,
                    "aliases": aliases,
                    "market": market,
                    "sector": str(old.get("sector", "")).strip(),
                    "industry": str(old.get("industry", "")).strip(),
                    "enabled": "1",
                })

        rows.sort(key=lambda row: (row["market"], row["ticker"]))
        tmp = output.with_suffix(output.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(output)
        print(f"[OK] KRX ticker master {snapshot_date}: {len(rows)} tickers -> {output}")
        return len(rows)
    except Exception as exc:
        if best_effort:
            print(f"[WARN] ticker master refresh skipped: {type(exc).__name__}: {exc}")
            print(f"[WARN] using existing ticker master: {output}")
            return 0
        raise


def main():
    parser = argparse.ArgumentParser(description="Build KOSPI/KOSDAQ ticker_master.csv from KRX via pykrx")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--if-stale-days", type=int, default=0)
    parser.add_argument("--best-effort", action="store_true")
    args = parser.parse_args()
    build(Path(args.output), if_stale_days=args.if_stale_days, best_effort=args.best_effort)


if __name__ == "__main__":
    main()
