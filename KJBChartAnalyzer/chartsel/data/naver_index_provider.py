from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


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


def normalize_index_code(value: str) -> str:
    key = str(value or "").strip().upper()
    if key not in _INDEX_CODES:
        raise ValueError(f"지원하지 않는 네이버 시장지수 코드입니다: {value}")
    return _INDEX_CODES[key]


def _number(text: str) -> float:
    raw = str(text or "").replace(",", "").replace("%", "").strip()
    return float(raw) if raw else float("nan")


def _parse_page(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, object]] = []

    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 6:
            continue
        date_text = cells[0]
        try:
            dt = pd.to_datetime(date_text, format="%Y.%m.%d", errors="raise")
        except Exception:
            continue

        close = _number(cells[1])
        change_rate = _number(cells[3])
        volume_thousand = _number(cells[4])
        trading_value_million = _number(cells[5])
        rows.append(
            {
                "Date": dt.normalize(),
                "Close": close,
                "Change_Rate": change_rate,
                # 네이버 표 단위: 천주 / 백만원. 내부에서는 실제 단위로 환산한다.
                "Volume": volume_thousand * 1_000.0,
                "Trading_Value": trading_value_million * 1_000_000.0,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume", "Trading_Value", "Change_Rate"]
        )

    out = pd.DataFrame(rows).set_index("Date").sort_index()
    out = out[~out.index.duplicated(keep="last")]

    # Naver의 index day 표는 일별 종가 중심 데이터다. KJB의 시장 레짐/상대강도는
    # Close 이동평균과 수익률을 사용하므로 지수에 한해 OHLC를 Close로 채운다.
    # 이 데이터는 개별 종목 캔들/고저가 분석에는 사용하지 않는다.
    out["Open"] = out["Close"]
    out["High"] = out["Close"]
    out["Low"] = out["Close"]
    return out[["Open", "High", "Low", "Close", "Volume", "Trading_Value", "Change_Rate"]]


def fetch_naver_index_ohlcv(
    index_code: str,
    start_date: str,
    end_date: str,
    *,
    timeout: float = 10.0,
    sleep_sec: float = 0.03,
    max_pages: int = 1000,
) -> pd.DataFrame:
    """네이버 금융 일별시세에서 KOSPI/KOSDAQ 종가 기반 시장 데이터를 조회한다.

    페이지는 최신일에서 과거 방향으로 내려간다. 요청 시작일보다 오래된 행이
    확인되면 추가 페이지 요청을 중단한다.
    """
    code = normalize_index_code(index_code)
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    if start_ts > end_ts:
        raise ValueError(f"start_date > end_date: {start_date} > {end_date}")

    session = requests.Session()
    session.headers.update(_HEADERS)
    frames: list[pd.DataFrame] = []

    for page in range(1, max_pages + 1):
        resp = session.get(
            _BASE_URL,
            params={"code": code, "page": page},
            timeout=timeout,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "euc-kr"
        frame = _parse_page(resp.text)
        if frame.empty:
            break

        frames.append(frame)
        oldest = pd.Timestamp(frame.index.min()).normalize()
        if oldest <= start_ts:
            break
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    if not frames:
        raise RuntimeError(f"네이버 시장지수 데이터가 비어 있습니다: {code}")

    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out.loc[(out.index >= start_ts) & (out.index <= end_ts)].copy()
    if out.empty:
        raise RuntimeError(
            f"네이버 시장지수 요청 기간에 데이터가 없습니다: {code} {start_date}~{end_date}"
        )
    return out
