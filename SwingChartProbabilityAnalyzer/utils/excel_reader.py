from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

TICKER_COLUMN_CANDIDATES = ["종목코드", "단축코드", "Ticker", "ticker", "Code", "code"]
NAME_COLUMN_CANDIDATES = ["종목명", "한글 종목약명", "한글 종목명", "Name", "name"]

SORT_COLUMN_ALIASES = {
    "market_cap": "시가총액", "marketcap": "시가총액", "시총": "시가총액", "시가총액": "시가총액",
    "trading_value": "거래대금", "거래대금": "거래대금",
    "volume": "거래량", "거래량": "거래량",
}


def normalize_ticker(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip().upper()
    if text.endswith(".0"):
        text = text[:-2]
    if text.isdigit():
        return text.zfill(6)
    if len(text) == 6 and text.isalnum():
        return text
    return None


def clean_numeric_series(series: pd.Series) -> pd.Series:
    cleaned = (series.astype(str).str.replace(",", "", regex=False)
               .str.replace("%", "", regex=False).str.replace("N/A", "", regex=False)
               .str.replace("nan", "", regex=False).str.strip())
    cleaned = cleaned.replace({"": pd.NA, "-": pd.NA, "--": pd.NA, "None": pd.NA})
    return pd.to_numeric(cleaned, errors="coerce")


def _find_first_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in df.columns), None)


def read_kospi_info_excel(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"KOSPI_Info.xlsx 파일을 찾을 수 없습니다: {source}")
    df = pd.read_excel(source, dtype={"종목코드": str, "단축코드": str})
    if df.empty:
        raise ValueError(f"KOSPI_Info.xlsx 파일이 비어 있습니다: {source}")
    ticker_col = _find_first_column(df, TICKER_COLUMN_CANDIDATES)
    if ticker_col is None:
        raise ValueError("종목코드 컬럼을 찾지 못했습니다.")
    name_col = _find_first_column(df, NAME_COLUMN_CANDIDATES) or ticker_col
    result = df.copy()
    result["Ticker"] = result[ticker_col].map(normalize_ticker)
    result["Name"] = result[name_col].fillna("").astype(str).str.strip()
    result = result[result["Ticker"].notna()].copy()
    result["Name"] = result["Name"].where(result["Name"].ne(""), result["Ticker"])
    return result


def resolve_sort_column(df: pd.DataFrame, sort_by: str) -> str:
    col = SORT_COLUMN_ALIASES.get(sort_by, sort_by)
    if col not in df.columns:
        raise ValueError(f"정렬 기준 컬럼 없음: {sort_by}; 사용 가능={list(df.columns)}")
    return col
