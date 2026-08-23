from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class SectorMapperConfig:
    """섹터/종목 매핑 파일 설정.

    기존 섹터 수급 분석기의 네이버 업종 매핑 규칙을 그대로 사용하고,
    백테스트에서 KOSPI/KOSDAQ 벤치마크를 구분하기 위해 Market 컬럼을 함께 보존한다.
    """

    kospi_info_path: str | Path
    upjong_info_path: str | Path | None = None
    ticker_col: str = "단축코드"
    name_col: str = "한글 종목명"
    sector_code_col: str = "네이버_업종번호"
    sector_name_col: str = "네이버_업종명"
    unknown_sector_name: str = "기타/미분류"


class SectorMapper:
    TICKER_CANDIDATES = ["단축코드", "종목코드", "Ticker", "ticker", "Code", "code", "Symbol", "symbol"]
    NAME_CANDIDATES = ["한글 종목명", "한글 종목약명", "종목명", "Name", "name", "Company_Name", "company_name"]
    MARKET_CANDIDATES = ["시장", "Market", "market", "시장구분", "시장명"]

    def __init__(self, config: SectorMapperConfig):
        self.config = config

    @staticmethod
    def normalize_ticker(value) -> str:
        if pd.isna(value):
            return ""
        value = str(value).strip()
        if value.endswith(".0"):
            value = value[:-2]
        value = re.sub(r"[^0-9]", "", value)
        return value.zfill(6) if value else ""

    @classmethod
    def _find_column(cls, df: pd.DataFrame, candidates: list[str], label: str) -> str:
        for col in candidates:
            if col in df.columns:
                return col
        raise ValueError(f"{label} 컬럼을 찾지 못했습니다. 현재 컬럼: {list(df.columns)}")

    @staticmethod
    def _clean_name(value) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip()

    @staticmethod
    def _normalize_market(value) -> str:
        text = str(value or "KOSPI").strip().upper()
        if "KOSDAQ" in text or "코스닥" in text:
            return "KOSDAQ"
        return "KOSPI"

    @staticmethod
    def make_common_stock_name(name: str) -> str:
        if not name:
            return ""
        text = str(name).strip()
        text = re.sub(r"\((신형|전환|종류주|상장지수|ETF|ETN).*?\)", "", text)
        text = re.sub(r"\d*우선주", "", text)
        text = re.sub(r"보통주$", "", text)
        text = re.sub(r"\d*우B?$", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def infer_special_sector(name: str) -> tuple[str | None, str | None]:
        if not name:
            return None, None
        text = str(name)
        if "리츠" in text:
            return "SPECIAL_REIT", "리츠"
        if "인프라" in text or "맥쿼리" in text:
            return "SPECIAL_INFRA", "인프라펀드"
        if "스팩" in text or "SPAC" in text.upper():
            return "SPECIAL_SPAC", "스팩"
        if any(keyword in text.upper() for keyword in ["ETF", "ETN", "KODEX", "TIGER", "ACE", "SOL", "KOSEF"]):
            return "SPECIAL_ETF", "ETF/ETN"
        return None, None

    def load_sector_map(self) -> pd.DataFrame:
        kospi_df = pd.read_excel(self.config.kospi_info_path)
        ticker_col = self._find_column(kospi_df, self.TICKER_CANDIDATES, "종목코드")
        name_col = self._find_column(kospi_df, self.NAME_CANDIDATES, "종목명")
        market_col = next((c for c in self.MARKET_CANDIDATES if c in kospi_df.columns), None)

        df = kospi_df.copy()
        df[ticker_col] = df[ticker_col].apply(self.normalize_ticker)
        df[name_col] = df[name_col].apply(self._clean_name)

        if self.config.sector_name_col not in df.columns and self.config.upjong_info_path:
            upjong_df = pd.read_excel(self.config.upjong_info_path)
            upjong_ticker_col = self._find_column(upjong_df, self.TICKER_CANDIDATES, "업종 매핑 종목코드")
            upjong_df[upjong_ticker_col] = upjong_df[upjong_ticker_col].apply(self.normalize_ticker)
            merge_cols = [upjong_ticker_col]
            for col in [self.config.sector_code_col, self.config.sector_name_col, "업종번호", "업종명"]:
                if col in upjong_df.columns and col not in merge_cols:
                    merge_cols.append(col)
            upjong_df = upjong_df[merge_cols].drop_duplicates(subset=[upjong_ticker_col])
            df = df.merge(upjong_df, left_on=ticker_col, right_on=upjong_ticker_col, how="left")
            if upjong_ticker_col != ticker_col and upjong_ticker_col in df.columns:
                df = df.drop(columns=[upjong_ticker_col])
            if self.config.sector_name_col not in df.columns and "업종명" in df.columns:
                df[self.config.sector_name_col] = df["업종명"]
            if self.config.sector_code_col not in df.columns and "업종번호" in df.columns:
                df[self.config.sector_code_col] = df["업종번호"]

        if self.config.sector_code_col not in df.columns:
            df[self.config.sector_code_col] = pd.NA
        if self.config.sector_name_col not in df.columns:
            df[self.config.sector_name_col] = pd.NA

        df[self.config.sector_code_col] = df[self.config.sector_code_col].astype("object")
        df[self.config.sector_name_col] = df[self.config.sector_name_col].astype("object")
        df = df.rename(columns={ticker_col: "Ticker", name_col: "Company_Name"})
        df["Ticker"] = df["Ticker"].apply(self.normalize_ticker)
        df["Company_Name"] = df["Company_Name"].apply(self._clean_name)
        if market_col and market_col in df.columns:
            df["Market"] = df[market_col].apply(self._normalize_market)
        else:
            df["Market"] = "KOSPI"

        df = self._fill_missing_sector(df)
        result_cols = ["Ticker", "Company_Name", "Market", self.config.sector_code_col, self.config.sector_name_col]
        return df[result_cols].drop_duplicates(subset=["Ticker"]).reset_index(drop=True)

    def _fill_missing_sector(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        sector_col = self.config.sector_name_col
        code_col = self.config.sector_code_col
        valid = result[result[sector_col].notna() & (result[sector_col].astype(str).str.strip() != "")].copy()
        valid["_common_name"] = valid["Company_Name"].apply(self.make_common_stock_name)
        name_to_sector = (
            valid.drop_duplicates(subset=["_common_name"])
            .set_index("_common_name")[[code_col, sector_col]]
            .to_dict(orient="index")
        )
        missing_mask = result[sector_col].isna() | (result[sector_col].astype(str).str.strip() == "")
        for idx in result[missing_mask].index:
            name = result.at[idx, "Company_Name"]
            common_name = self.make_common_stock_name(name)
            if common_name in name_to_sector:
                result.at[idx, code_col] = name_to_sector[common_name].get(code_col)
                result.at[idx, sector_col] = name_to_sector[common_name].get(sector_col)
                continue
            special_code, special_name = self.infer_special_sector(name)
            if special_name:
                result.at[idx, code_col] = special_code
                result.at[idx, sector_col] = special_name
                continue
            result.at[idx, code_col] = "UNKNOWN"
            result.at[idx, sector_col] = self.config.unknown_sector_name
        return result

    def save_sector_map(self, output_path: str | Path) -> pd.DataFrame:
        result = self.load_sector_map()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        result.to_excel(output_path, index=False)
        return result
