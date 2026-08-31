from __future__ import annotations


def load_pykrx(ticker: str, start: str, end: str):
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx is not installed. Run: pip install pykrx") from exc

    df = stock.get_market_ohlcv_by_date(start, end, ticker)
    if df.empty:
        raise RuntimeError(f"No OHLCV returned for ticker={ticker}, range={start}~{end}")
    return df.rename(columns={
        "시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"
    })[["open", "high", "low", "close", "volume"]]
