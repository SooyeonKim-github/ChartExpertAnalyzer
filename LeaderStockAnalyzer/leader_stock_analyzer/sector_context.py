from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .models import LeaderResult


def _period_return(df: pd.DataFrame, bars: int) -> float | None:
    if df is None or df.empty or "close" not in df.columns:
        return None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) <= bars or float(close.iloc[-bars - 1]) <= 0:
        return None
    return (float(close.iloc[-1]) / float(close.iloc[-bars - 1]) - 1.0) * 100.0


def _percentile(series: pd.Series) -> pd.Series:
    """Cross-sectional percentile with neutral 50 for unavailable observations."""
    numeric = pd.to_numeric(series, errors="coerce")
    out = pd.Series(50.0, index=series.index, dtype=float)
    valid = numeric.notna()
    count = int(valid.sum())
    if count == 1:
        out.loc[valid] = 100.0
    elif count > 1:
        out.loc[valid] = numeric.loc[valid].rank(method="average", pct=True) * 100.0
    return out


class SectorContextEngine:
    """Point-in-time sector context built from the screened trading-value universe.

    KRX sector classification is used only for membership. Strength, breadth and
    leader ranks are reconstructed from price/trading-value data available up to
    scan_date, so no future data is required.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.scfg = cfg.get("sector_context", {})

    def enrich(
        self,
        results: list[LeaderResult],
        daily_by_ticker: dict[str, pd.DataFrame],
        sector_map: dict[str, str],
        market_period_returns: dict[str, dict[int, float | None]],
    ) -> list[LeaderResult]:
        if not results or not self.scfg.get("enabled", True):
            return results

        rows: list[dict] = []
        for r in results:
            ticker = str(r.ticker).zfill(6)
            daily = daily_by_ticker.get(ticker, pd.DataFrame())
            sector = sector_map.get(ticker)
            rows.append(
                {
                    "ticker": ticker,
                    "market": r.market,
                    "sector": sector,
                    "ret_5d": _period_return(daily, 5),
                    "ret_20d": _period_return(daily, 20),
                    "return_pct": r.return_pct,
                    "trading_value": r.trading_value,
                }
            )

        frame = pd.DataFrame(rows).set_index("ticker")
        valid = frame[frame["sector"].notna() & (frame["sector"].astype(str).str.len() > 0)].copy()
        if valid.empty:
            return results

        group_keys = ["market", "sector"]
        sector_rows: list[dict] = []
        for (market, sector), grp in valid.groupby(group_keys, dropna=False):
            members = list(grp.index)
            ret5 = pd.to_numeric(grp["ret_5d"], errors="coerce").dropna()
            ret20 = pd.to_numeric(grp["ret_20d"], errors="coerce").dropna()
            sector_ret_5d = float(ret5.median()) if not ret5.empty else None
            sector_ret_20d = float(ret20.median()) if not ret20.empty else None
            market_ret_5d = market_period_returns.get(str(market), {}).get(5)
            market_ret_20d = market_period_returns.get(str(market), {}).get(20)
            rs5 = sector_ret_5d - market_ret_5d if sector_ret_5d is not None and market_ret_5d is not None else None
            rs20 = sector_ret_20d - market_ret_20d if sector_ret_20d is not None and market_ret_20d is not None else None
            breadth = float((pd.to_numeric(grp["return_pct"], errors="coerce") > 0).mean() * 100.0)

            turnover_series: list[pd.Series] = []
            for ticker in members:
                daily = daily_by_ticker.get(ticker, pd.DataFrame())
                if daily is None or daily.empty or "trading_value" not in daily.columns:
                    continue
                turnover_series.append(pd.to_numeric(daily["trading_value"], errors="coerce").rename(ticker))
            turnover_ratio = None
            if turnover_series:
                sector_daily = pd.concat(turnover_series, axis=1).sum(axis=1, min_count=1).dropna().sort_index()
                if not sector_daily.empty:
                    avg20 = float(sector_daily.tail(20).mean())
                    if avg20 > 0:
                        turnover_ratio = float(sector_daily.iloc[-1]) / avg20

            sector_rows.append(
                {
                    "market": market,
                    "sector": sector,
                    "sector_ret_5d": sector_ret_5d,
                    "sector_ret_20d": sector_ret_20d,
                    "sector_rs_5d": rs5,
                    "sector_rs_20d": rs20,
                    "sector_breadth": breadth,
                    "sector_turnover_ratio": turnover_ratio,
                    "sector_member_count": len(members),
                }
            )

        sector_df = pd.DataFrame(sector_rows)
        sector_df["rs5_pct"] = _percentile(sector_df["sector_rs_5d"])
        sector_df["rs20_pct"] = _percentile(sector_df["sector_rs_20d"])
        sector_df["turnover_pct"] = _percentile(sector_df["sector_turnover_ratio"])
        sector_df["breadth_pct"] = _percentile(sector_df["sector_breadth"])
        weights = self.scfg.get("strength_weights", {})
        sector_df["sector_strength_score"] = (
            sector_df["rs5_pct"] * float(weights.get("rs_5d", 0.35))
            + sector_df["rs20_pct"] * float(weights.get("rs_20d", 0.35))
            + sector_df["turnover_pct"] * float(weights.get("turnover", 0.20))
            + sector_df["breadth_pct"] * float(weights.get("breadth", 0.10))
        ).round(2)
        sector_df["sector_market_rank"] = sector_df["sector_strength_score"].rank(method="min", ascending=False).astype(int)
        sector_lookup = {
            (str(row["market"]), str(row["sector"])): row
            for _, row in sector_df.iterrows()
        }

        stock_context: dict[str, dict] = {}
        for (market, sector), grp in valid.groupby(group_keys, dropna=False):
            key = (str(market), str(sector))
            sector_row = sector_lookup[key]
            g = grp.copy()
            ret5 = pd.to_numeric(g["ret_5d"], errors="coerce")
            ret20 = pd.to_numeric(g["ret_20d"], errors="coerce")
            sector_ret5 = sector_row["sector_ret_5d"]
            sector_ret20 = sector_row["sector_ret_20d"]
            g["stock_vs_sector_rs_5d"] = ret5 - float(sector_ret5) if pd.notna(sector_ret5) else pd.Series(float("nan"), index=g.index)
            g["stock_vs_sector_rs_20d"] = ret20 - float(sector_ret20) if pd.notna(sector_ret20) else pd.Series(float("nan"), index=g.index)
            g["rs5_pct"] = _percentile(g["stock_vs_sector_rs_5d"])
            g["rs20_pct"] = _percentile(g["stock_vs_sector_rs_20d"])
            g["value_pct"] = _percentile(g["trading_value"])
            leader_weights = self.scfg.get("leader_weights", {})
            g["sector_leader_score"] = (
                g["rs20_pct"] * float(leader_weights.get("rs_20d", 0.50))
                + g["rs5_pct"] * float(leader_weights.get("rs_5d", 0.25))
                + g["value_pct"] * float(leader_weights.get("trading_value", 0.25))
            ).round(2)
            g["sector_leader_rank"] = g["sector_leader_score"].rank(method="min", ascending=False).astype(int)
            for ticker, row in g.iterrows():
                stock_context[str(ticker)] = {
                    "stock_return_5d": row["ret_5d"],
                    "stock_return_20d": row["ret_20d"],
                    "stock_vs_sector_rs_5d": row["stock_vs_sector_rs_5d"],
                    "stock_vs_sector_rs_20d": row["stock_vs_sector_rs_20d"],
                    "sector_leader_score": row["sector_leader_score"],
                    "sector_leader_rank": int(row["sector_leader_rank"]),
                }

        min_members = int(self.scfg.get("min_members", 2))
        out: list[LeaderResult] = []
        for r in results:
            ticker = str(r.ticker).zfill(6)
            sector = sector_map.get(ticker)
            srow = sector_lookup.get((str(r.market), str(sector))) if sector else None
            crow = stock_context.get(ticker, {})
            if srow is None:
                out.append(replace(r, sector=sector, sector_context_available=False, sector_context_reliable=False))
                continue
            member_count = int(srow["sector_member_count"])
            out.append(
                replace(
                    r,
                    sector=str(sector),
                    sector_context_available=True,
                    sector_context_reliable=member_count >= min_members,
                    stock_return_5d=_none_or_float(crow.get("stock_return_5d")),
                    stock_return_20d=_none_or_float(crow.get("stock_return_20d")),
                    sector_ret_5d=_none_or_float(srow["sector_ret_5d"]),
                    sector_ret_20d=_none_or_float(srow["sector_ret_20d"]),
                    sector_rs_5d=_none_or_float(srow["sector_rs_5d"]),
                    sector_rs_20d=_none_or_float(srow["sector_rs_20d"]),
                    stock_vs_sector_rs_5d=_none_or_float(crow.get("stock_vs_sector_rs_5d")),
                    stock_vs_sector_rs_20d=_none_or_float(crow.get("stock_vs_sector_rs_20d")),
                    sector_strength_score=_none_or_float(srow["sector_strength_score"]),
                    sector_market_rank=int(srow["sector_market_rank"]),
                    sector_leader_score=_none_or_float(crow.get("sector_leader_score")),
                    sector_leader_rank=int(crow.get("sector_leader_rank", 0) or 0),
                    sector_member_count=member_count,
                    sector_breadth=_none_or_float(srow["sector_breadth"]),
                    sector_turnover_ratio=_none_or_float(srow["sector_turnover_ratio"]),
                )
            )
        return out


def _none_or_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 3)
