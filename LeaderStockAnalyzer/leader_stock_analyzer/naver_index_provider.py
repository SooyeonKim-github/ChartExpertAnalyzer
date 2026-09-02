from __future__ import annotations

import time
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


_INDEX_CODES = {
    "^KS11": "KOSPI",
    "KOSPI": "KOSPI",
    "1001": "KOSPI",
    "^KQ11": "KOSDAQ",
    "KOSDAQ": "KOSDAQ",
    "2001": "KOSDAQ",
}

_BASE_URL = "https://finance.naver.com/sise/sise_index_day.naver"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}


class _NaverTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_tr = False
        self._in_td = False
        self._cells: list[str] = []
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._in_tr = True
            self._cells = []
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._in_td:
            text = str(data or "").strip()
            if text:
                self._chunks.append(text)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "td" and self._in_td:
            self._cells.append(" ".join(self._chunks).strip())
            self._chunks = []
            self._in_td = False
        elif tag == "tr" and self._in_tr:
            if self._cells:
                self.rows.append(self._cells)
            self._cells = []
            self._in_tr = False
            self._in_td = False


def normalize_index_code(value: str) -> str:
    key = str(value or "").strip().upper()
    if key not in _INDEX_CODES:
        raise ValueError(f"Unsupported Naver market index code: {value}")
    return _INDEX_CODES[key]


def _number(text: str) -> float:
    raw = str(text or "").replace(",", "").replace("%", "").strip()
    return float(raw) if raw else float("nan")


def _parse_page(html: str) -> pd.DataFrame:
    parser = _NaverTableParser()
    parser.feed(html)
    rows: list[dict[str, object]] = []

    for cells in parser.rows:
        if len(cells) < 6:
            continue
        try:
            dt = pd.to_datetime(cells[0], format="%Y.%m.%d", errors="raise")
        except Exception:
            continue

        rows.append(
            {
                "Date": dt.normalize(),
                "Close": _number(cells[1]),
                "Change_Rate": _number(cells[3]),
                "Volume": _number(cells[4]) * 1_000.0,
                "Trading_Value": _number(cells[5]) * 1_000_000.0,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Close", "Volume", "Trading_Value", "Change_Rate"])

    out = pd.DataFrame(rows).set_index("Date").sort_index()
    return out[~out.index.duplicated(keep="last")]


def _fetch_html(code: str, page: int, timeout: float) -> str:
    query = urlencode({"code": code, "page": int(page)})
    req = Request(f"{_BASE_URL}?{query}", headers=_HEADERS)
    with urlopen(req, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "euc-kr"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("euc-kr", errors="replace")


def fetch_naver_index_ohlcv(
    index_code: str,
    start_date: str,
    end_date: str,
    *,
    timeout: float = 10.0,
    sleep_sec: float = 0.03,
    max_pages: int = 1000,
) -> pd.DataFrame:
    code = normalize_index_code(index_code)
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    if start_ts > end_ts:
        raise ValueError(f"start_date > end_date: {start_date} > {end_date}")

    frames: list[pd.DataFrame] = []
    for page in range(1, max_pages + 1):
        frame = _parse_page(_fetch_html(code, page, timeout))
        if frame.empty:
            break
        frames.append(frame)
        if pd.Timestamp(frame.index.min()).normalize() <= start_ts:
            break
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    if not frames:
        raise RuntimeError(f"Naver market-index data is empty: {code}")

    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out.loc[(out.index >= start_ts) & (out.index <= end_ts)].copy()
    if out.empty:
        raise RuntimeError(f"No Naver market-index data in range: {code} {start_date}~{end_date}")
    return out
