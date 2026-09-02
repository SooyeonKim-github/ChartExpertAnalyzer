from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TICKER_COLUMNS = ["종목코드", "단축코드", "Ticker", "ticker", "Code", "code"]
NAME_COLUMNS = ["종목명", "한글 종목약명", "한글 종목명", "Name", "name"]
SORT_ALIASES = {"market_cap": "시가총액", "trading_value": "거래대금", "volume": "거래량"}
ETF_PREFIX = r"^(KODEX|TIGER|ACE|RISE|KBSTAR|SOL|PLUS|HANARO|TIMEFOLIO|KOACT|WOORI|ARIRANG|BNK|HK|VITA|히어로즈|마이다스)"


@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    name: str
    market: str
    market_cap: float | None = None
    trading_value: float | None = None
    volume: float | None = None
    source_rank: int | None = None


def normalize_ticker(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip().upper()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else None


def clean_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("N/A", "", regex=False)
        .str.strip(),
        errors="coerce",
    )


def read_universe_excel(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"종목 Universe Excel을 찾을 수 없습니다: {p}")
    raw = pd.read_excel(p, dtype=str)
    ticker_col = next((c for c in TICKER_COLUMNS if c in raw.columns), None)
    name_col = next((c for c in NAME_COLUMNS if c in raw.columns), None)
    if ticker_col is None:
        raise ValueError(f"종목코드 컬럼을 찾지 못했습니다: {list(raw.columns)}")
    name_col = name_col or ticker_col

    out = raw.copy()
    out["Ticker"] = out[ticker_col].map(normalize_ticker)
    out["Name"] = out[name_col].fillna("").astype(str).str.strip()
    out["market"] = out["시장"].fillna("KOSPI").astype(str).str.upper() if "시장" in out.columns else "KOSPI"
    out = out[out["Ticker"].notna()].drop_duplicates("Ticker", keep="first").copy()
    out["Name"] = out["Name"].where(out["Name"].ne(""), out["Ticker"])
    return out


def exclude_etf_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    name = out["Name"].fillna("").astype(str).str.upper()
    ticker = out["Ticker"].fillna("").astype(str).str.upper()
    market = out["market"].fillna("").astype(str).str.upper()
    mask = (
        market.str.contains("ETF|ETN|ETP", regex=True, na=False)
        | name.str.contains("ETF|ETN|ETP", regex=True, na=False)
        | name.str.match(ETF_PREFIX, na=False)
        | ~ticker.str.fullmatch(r"\d{6}", na=False)
    )
    return out[~mask].copy()


class ExcelUniverseService:
    def __init__(self, info_excel_path: str | Path) -> None:
        self.info_excel_path = Path(info_excel_path)
        self._cache: pd.DataFrame | None = None

    def load_universe_df(self) -> pd.DataFrame:
        if self._cache is None:
            self._cache = read_universe_excel(self.info_excel_path)
        return self._cache.copy()

    @staticmethod
    def _num(row: pd.Series, column: str) -> float | None:
        if column not in row.index:
            return None
        value = clean_numeric_series(pd.Series([row[column]])).iloc[0]
        return None if pd.isna(value) else float(value)

    def get_universe(
        self,
        top_n: int = 0,
        sort_by: str = "market_cap",
        include_etf: bool = False,
        markets: tuple[str, ...] | None = None,
    ) -> list[TickerInfo]:
        include_etf = include_etf or os.environ.get("INCLUDE_ETF", "").strip() == "1"
        df = self.load_universe_df()
        if not include_etf:
            df = exclude_etf_rows(df)
        if markets:
            allowed = {str(x).upper() for x in markets}
            df = df[df["market"].astype(str).str.upper().isin(allowed)].copy()

        if sort_by and top_n > 0:
            column = SORT_ALIASES.get(sort_by, sort_by)
            if column not in df.columns:
                raise ValueError(f"정렬 기준 컬럼 없음: {sort_by}; columns={list(df.columns)}")
            df["_sort"] = clean_numeric_series(df[column])
            df = df.sort_values("_sort", ascending=False, na_position="last")
        if top_n > 0:
            df = df.head(top_n)

        result: list[TickerInfo] = []
        for rank, (_, row) in enumerate(df.iterrows(), start=1):
            result.append(
                TickerInfo(
                    ticker=str(row["Ticker"]).zfill(6),
                    name=str(row["Name"]),
                    market=str(row.get("market", "KOSPI")).upper(),
                    market_cap=self._num(row, "시가총액"),
                    trading_value=self._num(row, "거래대금"),
                    volume=self._num(row, "거래량"),
                    source_rank=rank,
                )
            )
        return result
