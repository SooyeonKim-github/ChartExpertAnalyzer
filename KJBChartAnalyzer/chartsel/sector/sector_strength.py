from __future__ import annotations

import numpy as np
import pandas as pd


def _clamp(v, lo=-100.0, hi=100.0):
    try:
        if not np.isfinite(v):
            return 0.0
    except Exception:
        return 0.0
    return float(max(lo, min(hi, v)))


def _score_component(series: pd.Series, scale: float, cap: float) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    return (x / scale * cap).clip(-cap, cap).fillna(0.0)


def _rolling_down_hit(group: pd.DataFrame, window: int = 20) -> tuple[pd.Series, pd.Series]:
    """미래 데이터를 쓰지 않고 최근 window일 지수 하락일 방어 승률/평균 초과수익을 계산."""
    idx_out = pd.Series(np.nan, index=group.index, dtype=float)
    avg_out = pd.Series(np.nan, index=group.index, dtype=float)
    mr = pd.to_numeric(group["Market_Return"], errors="coerce")
    sr = pd.to_numeric(group["Sector_Return"], errors="coerce")
    for i in range(len(group)):
        lo = max(0, i - window + 1)
        m = mr.iloc[lo:i+1]
        s = sr.iloc[lo:i+1]
        mask = m < 0
        if int(mask.sum()) >= 3:
            excess = s[mask] - m[mask]
            idx_out.iloc[i] = float((s[mask] > m[mask]).mean())
            avg_out.iloc[i] = float(excess.mean())
    return idx_out, avg_out


class SectorStrengthScorer:
    """섹터 가격 상대강도 + 기존 수급점수를 결합한다.

    Sector_RS_Score: 가격 상대강도만 반영 (0~100)
    Sector_Flow_Score: 기존 수급 코드의 0~11 점수
    Sector_Composite_Score: 둘을 분리 보존한 뒤 가중 결합
    """

    def __init__(self, sector_col: str = "네이버_업종명", market_col: str = "Market", price_weight: float = 0.70, flow_weight: float = 0.30):
        self.sector_col = sector_col
        self.market_col = market_col
        total = max(1e-9, float(price_weight) + float(flow_weight))
        self.price_weight = float(price_weight) / total
        self.flow_weight = float(flow_weight) / total

    @staticmethod
    def benchmark_for_market(market: str) -> str:
        return "^KQ11" if "KOSDAQ" in str(market).upper() else "^KS11"

    def add_price_strength(self, flow_df: pd.DataFrame, benchmark_cache: dict[str, pd.DataFrame | None]) -> pd.DataFrame:
        if flow_df is None or flow_df.empty:
            return pd.DataFrame()
        df = flow_df.copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
        if self.market_col not in df.columns:
            df[self.market_col] = "KOSPI"
        group_cols = [self.market_col, self.sector_col]
        df = df.sort_values(group_cols + ["Date"]).reset_index(drop=True)

        # 동일가중 섹터 지수: 구성종목 평균 일수익률을 누적. 당시까지 알려진 일수익률만 사용한다.
        df["Sector_Return"] = pd.to_numeric(df["Avg_Return"], errors="coerce").fillna(0.0)
        df["Sector_Index"] = df.groupby(group_cols)["Sector_Return"].transform(lambda x: (1.0 + x.fillna(0.0)).cumprod() * 100.0)

        parts = []
        for market, mdf in df.groupby(self.market_col, sort=False):
            benchmark = self.benchmark_for_market(market)
            b = benchmark_cache.get(benchmark)
            x = mdf.copy()
            if b is None or b.empty or "Close" not in b.columns:
                x["Market_Close"] = np.nan
            else:
                bb = b[["Close"]].copy().reset_index()
                date_col = bb.columns[0]
                bb = bb.rename(columns={date_col: "Date", "Close": "Market_Close"})
                bb["Date"] = pd.to_datetime(bb["Date"]).dt.normalize()
                bb = bb.drop_duplicates("Date", keep="last")
                x = x.merge(bb[["Date", "Market_Close"]], on="Date", how="left")
            parts.append(x)
        df = pd.concat(parts, ignore_index=True).sort_values(group_cols + ["Date"]).reset_index(drop=True)
        df["Market_Return"] = df.groupby(group_cols)["Market_Close"].pct_change()

        for bars in (5, 20, 60):
            df[f"Sector_Return_{bars}D"] = df.groupby(group_cols)["Sector_Index"].pct_change(bars)
            df[f"Market_Return_{bars}D"] = df.groupby(group_cols)["Market_Close"].pct_change(bars)
            df[f"Sector_Rel_Return_{bars}D"] = df[f"Sector_Return_{bars}D"] - df[f"Market_Return_{bars}D"]

        dd_hit = pd.Series(np.nan, index=df.index)
        dd_avg = pd.Series(np.nan, index=df.index)
        for _, g in df.groupby(group_cols, sort=False):
            h, a = _rolling_down_hit(g, 20)
            dd_hit.loc[g.index] = h.values
            dd_avg.loc[g.index] = a.values
        df["Sector_Down_Day_Hit_Rate_20D"] = dd_hit
        df["Sector_Down_Day_Avg_Excess_20D"] = dd_avg

        # 현재값 / 최근 60일 고점 및 저점으로 낙폭/회복 우위 계산
        g = df.groupby(group_cols, group_keys=False)
        sector_max = g["Sector_Index"].transform(lambda x: x.rolling(61, min_periods=20).max())
        market_max = g["Market_Close"].transform(lambda x: x.rolling(61, min_periods=20).max())
        sector_min = g["Sector_Index"].transform(lambda x: x.rolling(61, min_periods=20).min())
        market_min = g["Market_Close"].transform(lambda x: x.rolling(61, min_periods=20).min())
        df["Sector_Drawdown_Advantage_60D"] = (df["Sector_Index"] / sector_max - 1.0) - (df["Market_Close"] / market_max - 1.0)
        df["Sector_Rebound_Advantage_60D"] = (df["Sector_Index"] / sector_min - 1.0) - (df["Market_Close"] / market_min - 1.0)

        # Stock RS와 같은 철학/스케일. 50점이 중립.
        comp = pd.DataFrame(index=df.index)
        comp["c5"] = _score_component(df["Sector_Rel_Return_5D"], 0.05, 7.5)
        comp["c20"] = _score_component(df["Sector_Rel_Return_20D"], 0.10, 15.0)
        comp["c60"] = _score_component(df["Sector_Rel_Return_60D"], 0.20, 12.5)
        comp["down_hit"] = ((pd.to_numeric(df["Sector_Down_Day_Hit_Rate_20D"], errors="coerce") - 0.5) * 20.0).clip(-10, 10).fillna(0.0)
        comp["down_avg"] = _score_component(df["Sector_Down_Day_Avg_Excess_20D"], 0.01, 7.5)
        comp["dd"] = _score_component(df["Sector_Drawdown_Advantage_60D"], 0.10, 10.0)
        comp["rebound"] = _score_component(df["Sector_Rebound_Advantage_60D"], 0.20, 7.5)
        df["Sector_RS_Score"] = (50.0 + comp.sum(axis=1)).clip(0, 100).round(2)
        df["Sector_RS_Available"] = df["Market_Close"].notna() & df["Sector_Rel_Return_20D"].notna()
        return df

    def add_composite_score(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        x = df.copy()
        if "Sector_Flow_Score_100" not in x.columns:
            x["Sector_Flow_Score_100"] = pd.to_numeric(x.get("Sector_Flow_Score", 0), errors="coerce").fillna(0) / 11.0 * 100.0
        rs = pd.to_numeric(x["Sector_RS_Score"], errors="coerce")
        flow = pd.to_numeric(x["Sector_Flow_Score_100"], errors="coerce")
        # 데이터 자체가 부족한 구간은 약함(0점)이 아니라 중립(50점)으로 처리한다.
        rs_available = x.get("Sector_RS_Available", pd.Series(True, index=x.index)).fillna(False).astype(bool)
        flow_available = x.get("Sector_Flow_Available", pd.Series(True, index=x.index)).fillna(False).astype(bool)
        rs_eff = rs.where(rs_available, 50.0).fillna(50.0)
        flow_eff = flow.where(flow_available, 50.0).fillna(50.0)
        x["Sector_Composite_Score"] = (rs_eff * self.price_weight + flow_eff * self.flow_weight).clip(0, 100).round(2)
        group_cols = ["Date"] + ([self.market_col] if self.market_col in x.columns else [])
        x["Sector_RS_Rank"] = x.groupby(group_cols)["Sector_RS_Score"].rank(method="min", ascending=False)
        x["Sector_Composite_Rank"] = x.groupby(group_cols)["Sector_Composite_Score"].rank(method="min", ascending=False)
        return x


def sector_leader_score(selection_score: float, stock_rs_score: float, sector_score: float | None, market_regime: str, cfg: dict | None = None) -> tuple[float, dict[str, float]]:
    """V3 Leader: Selection + Stock RS + Sector Composite.

    기존 leader_score는 그대로 남겨 V2와 V3를 동일 이벤트에서 비교할 수 있게 한다.
    sector_score가 없으면 Selection+Stock RS로 가중치를 재정규화한다.
    """
    cfg = cfg or {}
    regime = str(market_regime or "")
    if regime == "downtrend":
        weights = cfg.get("weights_downtrend", {"selection": 0.45, "stock_rs": 0.35, "sector": 0.20})
    elif regime == "volatile":
        weights = cfg.get("weights_volatile", {"selection": 0.50, "stock_rs": 0.30, "sector": 0.20})
    else:
        weights = cfg.get("weights_normal", {"selection": 0.55, "stock_rs": 0.30, "sector": 0.15})
    ws = float(weights.get("selection", 0.55))
    wr = float(weights.get("stock_rs", 0.30))
    wc = float(weights.get("sector", 0.15))
    valid_sector = sector_score is not None and np.isfinite(float(sector_score))
    if not valid_sector:
        total = max(1e-9, ws + wr)
        ws, wr, wc = ws / total, wr / total, 0.0
        sector_value = 50.0
    else:
        total = max(1e-9, ws + wr + wc)
        ws, wr, wc = ws / total, wr / total, wc / total
        sector_value = float(sector_score)
    score = float(selection_score) * ws + float(stock_rs_score) * wr + sector_value * wc
    score = round(max(0.0, min(100.0, score)), 2)
    return score, {"selection": round(ws, 3), "stock_rs": round(wr, 3), "sector": round(wc, 3)}
