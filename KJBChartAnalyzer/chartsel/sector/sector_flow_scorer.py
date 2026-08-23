from __future__ import annotations

import numpy as np
import pandas as pd


class SectorFlowScorer:
    """기존 섹터 수급 분석 점수를 백테스트용 일별 데이터에 부여한다."""

    def __init__(self, sector_col: str = "네이버_업종명", market_col: str = "Market"):
        self.sector_col = sector_col
        self.market_col = market_col

    def _sector_group_cols(self, df: pd.DataFrame) -> list[str]:
        return ([self.market_col] if self.market_col in df.columns else []) + [self.sector_col]

    def add_flow_indicators(self, sector_daily: pd.DataFrame) -> pd.DataFrame:
        if sector_daily is None or sector_daily.empty:
            return pd.DataFrame()
        df = sector_daily.copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
        group_cols = self._sector_group_cols(df)
        df = df.sort_values(group_cols + ["Date"])
        group = df.groupby(group_cols, group_keys=False)
        for window, min_periods in [(5, 3), (20, 10), (60, 20)]:
            df[f"TV_MA_{window}"] = group["Sector_Trading_Value"].transform(lambda x, w=window, m=min_periods: x.rolling(w, min_periods=m).mean())
            df[f"TV_Ratio_{window}"] = df["Sector_Trading_Value"] / df[f"TV_MA_{window}"]
            df[f"VOL_MA_{window}"] = group["Sector_Volume"].transform(lambda x, w=window, m=min_periods: x.rolling(w, min_periods=m).mean())
            df[f"VOL_Ratio_{window}"] = df["Sector_Volume"] / df[f"VOL_MA_{window}"]
        df["Avg_Return_5D"] = group["Avg_Return"].transform(lambda x: x.rolling(5, min_periods=3).mean())
        df["Avg_Return_20D"] = group["Avg_Return"].transform(lambda x: x.rolling(20, min_periods=10).mean())

        market_group = ["Date"] + ([self.market_col] if self.market_col in df.columns else [])
        market_daily = df.groupby(market_group).agg(
            Market_Trading_Value=("Sector_Trading_Value", "sum"),
            Market_Volume=("Sector_Volume", "sum"),
        ).reset_index().sort_values(market_group)
        rolling_group = [self.market_col] if self.market_col in market_daily.columns else []
        if rolling_group:
            mg = market_daily.groupby(rolling_group, group_keys=False)
            market_daily["Market_TV_MA_20"] = mg["Market_Trading_Value"].transform(lambda x: x.rolling(20, min_periods=10).mean())
            market_daily["Market_VOL_MA_20"] = mg["Market_Volume"].transform(lambda x: x.rolling(20, min_periods=10).mean())
        else:
            market_daily["Market_TV_MA_20"] = market_daily["Market_Trading_Value"].rolling(20, min_periods=10).mean()
            market_daily["Market_VOL_MA_20"] = market_daily["Market_Volume"].rolling(20, min_periods=10).mean()
        market_daily["Market_TV_Ratio_20"] = market_daily["Market_Trading_Value"] / market_daily["Market_TV_MA_20"]
        market_daily["Market_VOL_Ratio_20"] = market_daily["Market_Volume"] / market_daily["Market_VOL_MA_20"]
        merge_cols = market_group + ["Market_TV_Ratio_20", "Market_VOL_Ratio_20"]
        df = df.merge(market_daily[merge_cols], on=market_group, how="left")
        df["Relative_TV_Strength_20"] = df["TV_Ratio_20"] / df["Market_TV_Ratio_20"]
        df["Relative_VOL_Strength_20"] = df["VOL_Ratio_20"] / df["Market_VOL_Ratio_20"]
        numeric_cols = df.select_dtypes(include=["number"]).columns
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)
        return df

    def add_flow_score(self, flow_df: pd.DataFrame) -> pd.DataFrame:
        if flow_df is None or flow_df.empty:
            return pd.DataFrame()
        df = flow_df.copy()
        df["Sector_Flow_Score"] = 0
        df.loc[df["TV_Ratio_20"] >= 1.2, "Sector_Flow_Score"] += 1
        df.loc[df["TV_Ratio_20"] >= 1.5, "Sector_Flow_Score"] += 1
        df.loc[df["TV_Ratio_20"] >= 2.0, "Sector_Flow_Score"] += 1
        df.loc[df["VOL_Ratio_20"] >= 1.3, "Sector_Flow_Score"] += 1
        df.loc[df["VOL_Ratio_20"] >= 1.8, "Sector_Flow_Score"] += 1
        df.loc[df["Rising_Ratio"] >= 0.60, "Sector_Flow_Score"] += 1
        df.loc[df["Rising_Ratio"] >= 0.70, "Sector_Flow_Score"] += 1
        df.loc[df["Avg_Return"] > 0, "Sector_Flow_Score"] += 1
        df.loc[df["Avg_Return"] >= 0.02, "Sector_Flow_Score"] += 1
        df.loc[df["Relative_TV_Strength_20"] >= 1.2, "Sector_Flow_Score"] += 1
        df.loc[df["Relative_TV_Strength_20"] >= 1.5, "Sector_Flow_Score"] += 1
        conditions = [df["Sector_Flow_Score"] >= 8, df["Sector_Flow_Score"] >= 5, df["Sector_Flow_Score"] >= 3]
        df["Flow_Label"] = np.select(conditions, ["강한 수급 집중", "수급 유입", "관찰 필요"], default="수급 약함")
        df["Sector_Flow_Score_100"] = (pd.to_numeric(df["Sector_Flow_Score"], errors="coerce").fillna(0) / 11.0 * 100.0).clip(0, 100)
        df["Sector_Flow_Available"] = df["TV_Ratio_20"].notna() & df["VOL_Ratio_20"].notna() & df["Relative_TV_Strength_20"].notna()
        return df

    def add_daily_flow_rank(self, scored_df: pd.DataFrame) -> pd.DataFrame:
        if scored_df is None or scored_df.empty:
            return pd.DataFrame()
        df = scored_df.copy()
        group_cols = ["Date"] + ([self.market_col] if self.market_col in df.columns else [])
        df["Sector_Flow_Rank"] = df.groupby(group_cols)["Sector_Flow_Score"].rank(method="min", ascending=False)
        return df
