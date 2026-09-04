from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .models import LeaderResult


class PersistenceEngine:
    """Measure whether leadership has persisted across recent trading days.

    The engine reconstructs historical trading-value ranks inside the same
    point-in-time screened universe. This keeps the calculation self-contained
    and avoids dependency on previously generated Analyzer output files.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.pcfg = cfg.get("persistence", {})

    def enrich(
        self,
        results: list[LeaderResult],
        daily_by_ticker: dict[str, pd.DataFrame],
    ) -> list[LeaderResult]:
        if not results or not self.pcfg.get("enabled", True):
            return results

        value_series: dict[str, pd.Series] = {}
        return_series: dict[str, pd.Series] = {}
        for r in results:
            ticker = str(r.ticker).zfill(6)
            df = daily_by_ticker.get(ticker, pd.DataFrame())
            if df is None or df.empty:
                continue
            if "trading_value" in df.columns:
                value_series[ticker] = pd.to_numeric(df["trading_value"], errors="coerce").rename(ticker)
            if "close" in df.columns:
                close = pd.to_numeric(df["close"], errors="coerce")
                return_series[ticker] = close.pct_change(fill_method=None).mul(100.0).rename(ticker)

        if not value_series:
            return results

        value_df = pd.DataFrame(value_series).sort_index()
        rank_df = value_df.rank(axis=1, method="min", ascending=False, na_option="keep")
        ret_df = pd.DataFrame(return_series).reindex(value_df.index) if return_series else pd.DataFrame(index=value_df.index)

        lookback5 = int(self.pcfg.get("short_lookback", 5))
        lookback10 = int(self.pcfg.get("long_lookback", 10))
        top20 = int(self.pcfg.get("top_rank", 20))
        top50 = int(self.pcfg.get("broad_rank", 50))
        strong_return = float(self.pcfg.get("strong_return_pct", 3.0))
        high_threshold = float(self.pcfg.get("high_score", 70.0))
        medium_threshold = float(self.pcfg.get("medium_score", 45.0))

        out: list[LeaderResult] = []
        for r in results:
            ticker = str(r.ticker).zfill(6)
            if ticker not in rank_df.columns:
                out.append(r)
                continue

            ranks = pd.to_numeric(rank_df[ticker], errors="coerce").dropna()
            ranks5 = ranks.tail(lookback5)
            ranks10 = ranks.tail(lookback10)
            if ranks5.empty:
                out.append(r)
                continue

            top20_days_5d = int((ranks5 <= top20).sum())
            top50_days_10d = int((ranks10 <= top50).sum()) if not ranks10.empty else 0
            avg_rank_5d = float(ranks5.mean())

            rets = pd.to_numeric(ret_df[ticker], errors="coerce").dropna() if ticker in ret_df.columns else pd.Series(dtype=float)
            rets5 = rets.tail(lookback5)
            strong_days_5d = int((rets5 >= strong_return).sum()) if not rets5.empty else 0

            short_days = max(1, len(ranks5))
            long_days = max(1, len(ranks10))
            ret_days = max(1, len(rets5))

            top20_component = min(1.0, top20_days_5d / short_days) * 40.0

            recent_counts = rank_df.loc[ranks5.index].notna().sum(axis=1)
            mean_universe = max(1.0, float(recent_counts.mean())) if not recent_counts.empty else float(len(results))
            if mean_universe <= 1:
                rank_quality = 1.0
            else:
                rank_quality = max(0.0, min(1.0, 1.0 - ((avg_rank_5d - 1.0) / (mean_universe - 1.0))))
            rank_component = rank_quality * 30.0

            strong_component = min(1.0, strong_days_5d / ret_days) * 20.0
            broad_component = min(1.0, top50_days_10d / long_days) * 10.0
            score = round(top20_component + rank_component + strong_component + broad_component, 2)

            if score >= high_threshold:
                level = "HIGH"
            elif score >= medium_threshold:
                level = "MEDIUM"
            else:
                level = "LOW"

            out.append(
                replace(
                    r,
                    persistence_available=True,
                    leader_persistence_score=score,
                    leader_persistence_level=level,
                    turnover_rank_avg_5d=round(avg_rank_5d, 2),
                    turnover_top20_days_5d=top20_days_5d,
                    turnover_top50_days_10d=top50_days_10d,
                    strong_return_days_5d=strong_days_5d,
                )
            )
        return out
