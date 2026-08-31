from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAJOR_US_EXCHANGES = {"NMS", "NGM", "NCM", "NYQ", "ASE"}


def _number(value) -> float | None:
    if isinstance(value, dict):
        value = value.get("raw", value.get("fmt"))
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _market_cap(quote: dict) -> float | None:
    for key in (
        "marketCap",
        "intradaymarketcap",
        "lastclosemarketcap.lasttwelvemonths",
        "lastclosemarketcap",
    ):
        n = _number(quote.get(key))
        if n is not None:
            return n
    return None


def _exchange_code(quote: dict) -> str:
    raw = str(
        quote.get("exchange")
        or quote.get("exchangeCode")
        or quote.get("fullExchangeName")
        or ""
    ).strip().upper()
    aliases = {
        "NASDAQGS": "NMS",
        "NASDAQGM": "NGM",
        "NASDAQCM": "NCM",
        "NASDAQ GLOBAL SELECT MARKET": "NMS",
        "NASDAQ GLOBAL MARKET": "NGM",
        "NASDAQ CAPITAL MARKET": "NCM",
        "NYSE": "NYQ",
        "NEW YORK STOCK EXCHANGE": "NYQ",
        "NYSE AMERICAN": "ASE",
    }
    return aliases.get(raw, raw)


def _fetch_quotes(fetch_limit: int) -> list[dict]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is required. Run: python -m pip install -U yfinance"
        ) from exc

    if not hasattr(yf, "screen") or not hasattr(yf, "EquityQuery"):
        raise RuntimeError(
            "Installed yfinance is too old for the screener API. "
            "Run: python -m pip install -U yfinance"
        )

    query = yf.EquityQuery("eq", ["region", "us"])
    quotes: list[dict] = []
    offset = 0
    page_size = 250

    while offset < fetch_limit:
        size = min(page_size, fetch_limit - offset)
        response = yf.screen(
            query,
            offset=offset,
            size=size,
            sortField="intradaymarketcap",
            sortAsc=False,
        )
        page = list((response or {}).get("quotes") or [])
        if not page:
            break
        quotes.extend(page)
        if len(page) < size:
            break
        offset += size
    return quotes


def build_universe(top_n: int, fetch_limit: int) -> list[dict]:
    quotes = _fetch_quotes(max(fetch_limit, top_n))
    candidates: list[dict] = []
    seen: set[str] = set()

    for quote in quotes:
        symbol = str(quote.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue

        quote_type = str(quote.get("quoteType") or "EQUITY").upper()
        if quote_type and quote_type != "EQUITY":
            continue

        exchange = _exchange_code(quote)
        # Yahoo's screener can include OTC names in region=us. Keep the main
        # Nasdaq/NYSE/NYSE American equity venues only.
        if exchange not in MAJOR_US_EXCHANGES:
            continue

        market_cap = _market_cap(quote)
        if market_cap is None:
            continue

        price = _number(quote.get("regularMarketPrice"))
        volume = _number(quote.get("regularMarketVolume"))
        name = str(
            quote.get("shortName")
            or quote.get("longName")
            or quote.get("displayName")
            or symbol
        ).strip()
        seen.add(symbol)
        candidates.append(
            {
                "ticker": symbol,
                "name": name or symbol,
                "market": "US",
                "exchange": exchange,
                "market_cap": market_cap,
                "price": price,
                "volume": volume,
                "trading_value": (price * volume) if price is not None and volume is not None else None,
            }
        )

    candidates.sort(key=lambda x: (x["market_cap"], x["ticker"]), reverse=True)
    selected = candidates[:top_n]
    for rank, row in enumerate(selected, start=1):
        row["source_rank"] = rank
        row["as_of_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return selected


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build current US equity market-cap TOP N universe.")
    p.add_argument("--top-n", type=int, default=300)
    p.add_argument(
        "--fetch-limit",
        type=int,
        default=1000,
        help="Yahoo rows fetched before main-exchange filtering. Default 1000.",
    )
    p.add_argument("--out-csv", default=str(ROOT / "data" / "us_marketcap_top300.csv"))
    p.add_argument("--out-txt", default=str(ROOT / "data" / "us_marketcap_top300.txt"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.top_n <= 0:
        raise ValueError("--top-n must be positive")

    rows = build_universe(args.top_n, max(args.fetch_limit, args.top_n + 200))
    if len(rows) < args.top_n:
        raise RuntimeError(
            f"Only {len(rows)} eligible main-exchange US stocks were returned; "
            f"requested TOP {args.top_n}. Try --fetch-limit 1500 or upgrade yfinance."
        )

    import pandas as pd

    out_csv = Path(args.out_csv)
    out_txt = Path(args.out_txt)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_txt.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "source_rank",
        "ticker",
        "name",
        "market",
        "exchange",
        "market_cap",
        "price",
        "volume",
        "trading_value",
        "as_of_utc",
    ]
    pd.DataFrame(rows)[columns].to_csv(out_csv, index=False, encoding="utf-8-sig")
    out_txt.write_text("\n".join(row["ticker"] for row in rows) + "\n", encoding="utf-8")

    print(f"[DONE] US market-cap TOP {len(rows)} -> {out_csv}")
    print(f"[DONE] Ticker list -> {out_txt}")
    print("[INFO] Main exchanges: NASDAQ + NYSE + NYSE American")
    print("[INFO] Universe is a CURRENT market-cap snapshot, not historical point-in-time membership.")
    print("[TOP 10]")
    for row in rows[:10]:
        print(
            f"  {row['source_rank']:>3}. {row['ticker']:<7} "
            f"{row['name'][:32]:<32} market_cap={row['market_cap']:,.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
