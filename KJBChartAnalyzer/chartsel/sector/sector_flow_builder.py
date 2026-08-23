from __future__ import annotations

from pathlib import Path
import pandas as pd

from .sector_mapper import SectorMapper


class SectorFlowBuilder:
    """종목별 일봉을 일자/시장/섹터 단위로 집계한다.

    기존 수급 분석 코드의 거래대금/거래량/Rising Ratio/평균수익률 집계를 유지한다.
    백테스트에서는 이미 조회한 price_cache를 재사용하므로 외부 재조회가 필요 없다.
    """

    def __init__(self, sector_map_df: pd.DataFrame, sector_col: str = "네이버_업종명", market_col: str = "Market"):
        self.sector_col = sector_col
        self.market_col = market_col
        self.sector_map_df = sector_map_df.copy()
        self.sector_map_df["Ticker"] = self.sector_map_df["Ticker"].apply(SectorMapper.normalize_ticker)
        if self.market_col not in self.sector_map_df.columns:
            self.sector_map_df[self.market_col] = "KOSPI"

    @staticmethod
    def _standardize_ohlcv(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        result = df.copy()
        if "Date" not in result.columns:
            result = result.reset_index()
        rename_map = {
            "날짜": "Date", "시가": "Open", "고가": "High", "저가": "Low", "종가": "Close",
            "거래량": "Volume", "거래대금": "Trading_Value", "등락률": "Change_Rate",
            "date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close",
            "volume": "Volume", "trading_value": "Trading_Value",
            "index": "Date",
        }
        result = result.rename(columns=rename_map)
        if "Date" not in result.columns:
            # reset_index() 후 인덱스 이름이 다른 경우 첫 컬럼을 날짜로 간주
            result = result.rename(columns={result.columns[0]: "Date"})
        result["Date"] = pd.to_datetime(result["Date"]).dt.normalize()
        result["Ticker"] = SectorMapper.normalize_ticker(ticker)
        for col in ["Open", "High", "Low", "Close", "Volume", "Trading_Value", "Change_Rate"]:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce")
        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [c for c in required if c not in result.columns]
        if missing:
            raise ValueError(f"일봉 데이터 필수 컬럼 누락: {missing}")
        if "Trading_Value" not in result.columns:
            result["Trading_Value"] = result["Close"] * result["Volume"]
        keep = ["Date", "Ticker", "Open", "High", "Low", "Close", "Volume", "Trading_Value"]
        if "Change_Rate" in result.columns:
            keep.append("Change_Rate")
        return result[keep].sort_values("Date").drop_duplicates(["Date", "Ticker"])

    @classmethod
    def from_price_cache(cls, price_cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
        all_prices = []
        for ticker, df in price_cache.items():
            try:
                x = cls._standardize_ohlcv(df, ticker)
                if not x.empty:
                    all_prices.append(x)
            except Exception:
                continue
        return pd.concat(all_prices, ignore_index=True) if all_prices else pd.DataFrame()

    def build_sector_daily_flow(self, price_df: pd.DataFrame) -> pd.DataFrame:
        if price_df is None or price_df.empty:
            return pd.DataFrame()
        df = price_df.copy()
        df["Ticker"] = df["Ticker"].apply(SectorMapper.normalize_ticker)
        df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
        for col in ["Open", "High", "Low", "Close", "Volume", "Trading_Value"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if "Trading_Value" not in df.columns:
            df["Trading_Value"] = df["Close"] * df["Volume"]
        df = df.merge(self.sector_map_df, on="Ticker", how="left")
        df[self.sector_col] = df[self.sector_col].fillna("기타/미분류")
        df[self.market_col] = df[self.market_col].fillna("KOSPI")
        df = df.sort_values(["Ticker", "Date"])
        df["Prev_Close"] = df.groupby("Ticker")["Close"].shift(1)
        df["Return"] = df["Close"] / df["Prev_Close"] - 1
        df["Is_Rising"] = df["Return"] > 0
        group_cols = ["Date", self.market_col, self.sector_col]
        sector_daily = df.groupby(group_cols, dropna=False).agg(
            Sector_Volume=("Volume", "sum"),
            Sector_Trading_Value=("Trading_Value", "sum"),
            Stock_Count=("Ticker", "nunique"),
            Rising_Stock_Count=("Is_Rising", "sum"),
            Avg_Return=("Return", "mean"),
            Median_Return=("Return", "median"),
        ).reset_index()
        sector_daily["Rising_Ratio"] = (sector_daily["Rising_Stock_Count"] / sector_daily["Stock_Count"]).fillna(0)
        return sector_daily.sort_values([self.market_col, self.sector_col, "Date"]).reset_index(drop=True)

    @staticmethod
    def load_daily_price_dir(daily_price_dir: str | Path) -> pd.DataFrame:
        daily_price_dir = Path(daily_price_dir)
        all_dfs = []
        for file_path in sorted(daily_price_dir.glob("*.csv")):
            try:
                all_dfs.append(SectorFlowBuilder._standardize_ohlcv(pd.read_csv(file_path), file_path.stem))
            except Exception as exc:
                print(f"[load skip] {file_path.name} | {exc}")
        return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
