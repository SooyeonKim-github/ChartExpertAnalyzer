from __future__ import annotations

import time
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import pandas as pd

_INDEX_CODES = {
    "^KS11": "KOSPI", "KOSPI": "KOSPI", "1001": "KOSPI",
    "^KQ11": "KOSDAQ", "KOSDAQ": "KOSDAQ", "2001": "KOSDAQ",
}
_BASE_URL = "https://finance.naver.com/sise/sise_index_day.naver"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self._cells, self._chunks = [], [], []
        self._in_tr = self._in_td = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self._in_tr, self._cells = True, []
        elif tag == "td" and self._in_tr:
            self._in_td, self._chunks = True, []

    def handle_data(self, data):
        if self._in_td and str(data).strip():
            self._chunks.append(str(data).strip())

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "td" and self._in_td:
            self._cells.append(" ".join(self._chunks).strip())
            self._in_td = False
        elif tag == "tr" and self._in_tr:
            if self._cells:
                self.rows.append(self._cells)
            self._in_tr = self._in_td = False


def _number(text: str) -> float:
    raw = str(text or "").replace(",", "").replace("%", "").strip()
    return float(raw) if raw else float("nan")


def _parse_page(html: str) -> pd.DataFrame:
    p = _Parser()
    p.feed(html)
    rows = []
    for cells in p.rows:
        if len(cells) < 6:
            continue
        try:
            dt = pd.to_datetime(cells[0], format="%Y.%m.%d", errors="raise")
        except Exception:
            continue
        close = _number(cells[1])
        rows.append({
            "Date": dt.normalize(),
            "Open": close, "High": close, "Low": close, "Close": close,
            "Volume": _number(cells[4]) * 1_000.0,
            "Trading_Value": _number(cells[5]) * 1_000_000.0,
            "Change_Rate": _number(cells[3]),
        })
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Trading_Value", "Change_Rate"])
    return pd.DataFrame(rows).set_index("Date").sort_index()


def fetch_naver_index_ohlcv(index_code: str, start_date: str, end_date: str, timeout: float = 10.0) -> pd.DataFrame:
    key = str(index_code).strip().upper()
    if key not in _INDEX_CODES:
        raise ValueError(f"지원하지 않는 지수 코드: {index_code}")
    code = _INDEX_CODES[key]
    start, end = pd.Timestamp(start_date).normalize(), pd.Timestamp(end_date).normalize()
    frames = []
    for page in range(1, 1001):
        req = Request(f"{_BASE_URL}?{urlencode({'code': code, 'page': page})}", headers=_HEADERS)
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "euc-kr"
        frame = _parse_page(raw.decode(charset, errors="replace"))
        if frame.empty:
            break
        frames.append(frame)
        if frame.index.min() <= start:
            break
        time.sleep(0.03)
    if not frames:
        raise RuntimeError(f"네이버 시장지수 데이터가 비어 있습니다: {code}")
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out.loc[(out.index >= start) & (out.index <= end)].copy()
    if out.empty:
        raise RuntimeError(f"시장지수 요청 기간 데이터 없음: {code} {start_date}~{end_date}")
    return out
