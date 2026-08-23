from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .sector_mapper import SectorMapper, SectorMapperConfig
from .sector_flow_builder import SectorFlowBuilder
from .sector_flow_scorer import SectorFlowScorer
from .sector_strength import SectorStrengthScorer


class SectorBacktestService:
    """백테스트용 섹터 컨텍스트를 한 번 생성하고 날짜/종목별로 빠르게 조회한다."""

    def __init__(self, info_excel_path: str | Path, cfg: dict | None = None):
        self.cfg = cfg or {}
        self.sector_col = self.cfg.get("sector_name_col", "네이버_업종명")
        self.market_col = "Market"
        upjong = self.cfg.get("upjong_info_path") or None
        mapper_cfg = SectorMapperConfig(
            kospi_info_path=info_excel_path,
            upjong_info_path=upjong,
            sector_code_col=self.cfg.get("sector_code_col", "네이버_업종번호"),
            sector_name_col=self.sector_col,
            unknown_sector_name=self.cfg.get("unknown_sector_name", "기타/미분류"),
        )
        self.mapper = SectorMapper(mapper_cfg)
        self.sector_map_df = pd.DataFrame()
        self.sector_daily_df = pd.DataFrame()
        self._ticker_map: dict[str, dict] = {}
        self._daily_lookup: dict[tuple[pd.Timestamp, str, str], dict] = {}
        self.aggregation_scope: str = 'none'

    def build(
        self,
        price_cache: dict[str, pd.DataFrame],
        benchmark_cache: dict[str, pd.DataFrame | None],
        allowed_tickers: set[str] | None = None,
        external_price_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        # 매핑은 전체를 보존한다. current Universe 종목 lookup에도 필요하고,
        # full-market cache가 있으면 섹터 전체 구성종목으로 집계하기 위해서다.
        self.sector_map_df = self.mapper.load_sector_map()
        valid_sector = self.sector_map_df[self.sector_col].fillna("").astype(str)
        valid_sector = valid_sector[~valid_sector.isin(["", self.cfg.get("unknown_sector_name", "기타/미분류")])]
        if valid_sector.empty:
            raise ValueError(
                f"{self.sector_col} 업종 매핑이 없습니다. KOSPI_Info 파일에 업종 컬럼을 넣거나 "
                "sector_strength.upjong_info_path를 지정하세요."
            )
        self._ticker_map = self.sector_map_df.set_index("Ticker").to_dict(orient="index") if not self.sector_map_df.empty else {}

        current_price_df = SectorFlowBuilder.from_price_cache(price_cache)
        if external_price_df is not None and not external_price_df.empty:
            # 기존 섹터 분석의 전체 종목 캐시를 기본으로 쓰고, 현재 백테스트에서 방금 조회한
            # Universe 데이터가 더 최신일 수 있으므로 동일 Date/Ticker는 current cache로 덮어쓴다.
            price_df = pd.concat([external_price_df, current_price_df], ignore_index=True)
            price_df["Ticker"] = price_df["Ticker"].apply(SectorMapper.normalize_ticker)
            price_df["Date"] = pd.to_datetime(price_df["Date"]).dt.normalize()
            price_df = price_df.drop_duplicates(["Date", "Ticker"], keep="last")
            map_for_builder = self.sector_map_df
            self.aggregation_scope = "full_market_cache"
        else:
            price_df = current_price_df
            map_for_builder = self.sector_map_df
            if allowed_tickers is not None:
                map_for_builder = map_for_builder[map_for_builder["Ticker"].isin(allowed_tickers)].copy()
            self.aggregation_scope = "backtest_universe"

        builder = SectorFlowBuilder(map_for_builder, sector_col=self.sector_col, market_col=self.market_col)
        daily = builder.build_sector_daily_flow(price_df)
        if daily.empty:
            return daily
        flow = SectorFlowScorer(self.sector_col, self.market_col)
        daily = flow.add_flow_indicators(daily)
        daily = flow.add_flow_score(daily)
        daily = flow.add_daily_flow_rank(daily)
        strength = SectorStrengthScorer(
            self.sector_col,
            self.market_col,
            price_weight=float(self.cfg.get("price_weight", 0.70)),
            flow_weight=float(self.cfg.get("flow_weight", 0.30)),
        )
        daily = strength.add_price_strength(daily, benchmark_cache)
        daily = strength.add_composite_score(daily)
        daily["Aggregation_Scope"] = self.aggregation_scope
        self.sector_daily_df = daily
        self._daily_lookup = {}
        for _, r in daily.iterrows():
            key = (pd.Timestamp(r["Date"]).normalize(), str(r[self.market_col]), str(r[self.sector_col]))
            self._daily_lookup[key] = r.to_dict()
        return daily

    def ticker_sector(self, ticker: str, fallback_market: str = "KOSPI") -> tuple[str, str]:
        item = self._ticker_map.get(str(ticker).zfill(6), {})
        return str(item.get(self.sector_col, "기타/미분류")), str(item.get(self.market_col, fallback_market))

    def context(self, ticker: str, date, fallback_market: str = "KOSPI") -> dict:
        sector, mapped_market = self.ticker_sector(ticker, fallback_market)
        market = "KOSDAQ" if "KOSDAQ" in str(fallback_market).upper() else (mapped_market or "KOSPI")
        key = (pd.Timestamp(date).normalize(), market, sector)
        row = self._daily_lookup.get(key)
        if row is None and mapped_market != market:
            row = self._daily_lookup.get((pd.Timestamp(date).normalize(), mapped_market, sector))
        if row is None:
            return {
                "sector_name": sector, "sector_rs_score": np.nan, "sector_composite_score": np.nan,
                "sector_rs_rank": np.nan, "sector_composite_rank": np.nan, "sector_flow_score": np.nan,
                "sector_flow_rank": np.nan, "sector_flow_label": "", "sector_rs_available": False,
                "sector_flow_available": False, "sector_aggregation_scope": self.aggregation_scope,
            }
        return {
            "sector_name": sector,
            "sector_rs_score": row.get("Sector_RS_Score", np.nan),
            "sector_composite_score": row.get("Sector_Composite_Score", np.nan),
            "sector_rs_rank": row.get("Sector_RS_Rank", np.nan),
            "sector_composite_rank": row.get("Sector_Composite_Rank", np.nan),
            "sector_flow_score": row.get("Sector_Flow_Score", np.nan),
            "sector_flow_score_100": row.get("Sector_Flow_Score_100", np.nan),
            "sector_flow_available": bool(row.get("Sector_Flow_Available", False)),
            "sector_flow_rank": row.get("Sector_Flow_Rank", np.nan),
            "sector_flow_label": row.get("Flow_Label", ""),
            "sector_rs_available": bool(row.get("Sector_RS_Available", False)),
            "sector_rel_return_5d": row.get("Sector_Rel_Return_5D", np.nan),
            "sector_rel_return_20d": row.get("Sector_Rel_Return_20D", np.nan),
            "sector_rel_return_60d": row.get("Sector_Rel_Return_60D", np.nan),
            "sector_down_day_hit_rate_20d": row.get("Sector_Down_Day_Hit_Rate_20D", np.nan),
            "sector_drawdown_advantage_60d": row.get("Sector_Drawdown_Advantage_60D", np.nan),
            "sector_rebound_advantage_60d": row.get("Sector_Rebound_Advantage_60D", np.nan),
            "sector_tv_ratio_20": row.get("TV_Ratio_20", np.nan),
            "sector_relative_tv_strength_20": row.get("Relative_TV_Strength_20", np.nan),
            "sector_rising_ratio": row.get("Rising_Ratio", np.nan),
            "sector_aggregation_scope": row.get("Aggregation_Scope", self.aggregation_scope),
        }
