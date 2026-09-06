from __future__ import annotations

from pathlib import Path

import pandas as pd

from .analyzer import LeaderStockAnalyzer
from .data_provider import PyKrxLeaderDataProvider
from .emerging import EmergingLeaderEngine
from .exhaustion import ExhaustionRiskEngine
from .leadership_history import LeadershipHistoryContext
from .lifecycle import LeaderLifecycleEngine
from .models import LeaderResult
from .persistence import PersistenceEngine
from .sector_context import SectorContextEngine


def _resolve_return_pct(row: pd.Series, daily: pd.DataFrame) -> float:
    value = pd.to_numeric(pd.Series([row.get("return_pct")]), errors="coerce").iloc[0]
    if pd.notna(value):
        return float(value)

    close = pd.to_numeric(daily.get("close"), errors="coerce").dropna()
    if len(close) >= 2 and float(close.iloc[-2]) > 0:
        return (float(close.iloc[-1]) / float(close.iloc[-2]) - 1.0) * 100.0
    return 0.0


def screen_date(
    cfg: dict,
    *,
    scan_date: str | None = None,
    top_n: int | None = None,
    base_dir: str | Path,
    progress: bool = True,
    provider: PyKrxLeaderDataProvider | None = None,
    lifecycle_engine: LeaderLifecycleEngine | None = None,
) -> tuple[str, list[LeaderResult]]:
    provider = provider or PyKrxLeaderDataProvider(cfg, base_dir)
    resolved = provider.resolve_scan_date(scan_date)
    universe = provider.build_universe(resolved, top_n=top_n)
    analyzer = LeaderStockAnalyzer(cfg)
    market_returns = {
        m: provider.get_market_return(m, resolved) for m in ["KOSPI", "KOSDAQ"]
    }

    raw_results: list[LeaderResult] = []
    daily_by_ticker: dict[str, pd.DataFrame] = {}
    total = len(universe)
    for idx, (ticker, row) in enumerate(universe.iterrows(), start=1):
        try:
            daily = provider.get_daily(ticker, resolved)
            daily = daily[daily.index <= pd.Timestamp(resolved)].copy()
            if len(daily) < 21:
                continue
            daily_by_ticker[str(ticker).zfill(6)] = daily
            intraday = provider.get_intraday(ticker, resolved)
            return_pct = _resolve_return_pct(row, daily)
            result = analyzer.analyze_one(
                scan_date=resolved,
                ticker=ticker,
                name=str(row["name"]),
                market=str(row["market"]),
                price=float(row["price"]),
                return_pct=return_pct,
                trading_value=float(row["trading_value"]),
                trading_value_rank=int(row["trading_value_rank"]),
                universe_size=total,
                daily=daily,
                intraday=intraday,
                market_return_pct=market_returns.get(str(row["market"])),
            )
            raw_results.append(result)
        except Exception as exc:
            if progress:
                print(f"[WARN] {ticker} {row.get('name', '')}: {exc}")
        if progress and (idx == total or idx % 10 == 0):
            print(f"[INFO] analyzed {idx}/{total}")

    enriched = raw_results
    if raw_results:
        sector_map = provider.get_sector_map(resolved)
        market_period_returns = {
            market: {
                3: provider.get_market_period_return(market, resolved, 3),
                5: provider.get_market_period_return(market, resolved, 5),
                20: provider.get_market_period_return(market, resolved, 20),
            }
            for market in ("KOSPI", "KOSDAQ")
        }

        # During range scans use the full preloaded candidate pool (normally
        # TOP100 * candidate_multiplier=3), not only today's final TOP100.
        # A standalone screen falls back to today's analyzed universe.
        history_frames = getattr(provider, "_range_price_cache", None) or daily_by_ticker
        history = LeadershipHistoryContext.build(
            history_frames,
            scan_date=resolved,
        )

        enriched = SectorContextEngine(cfg).enrich(
            enriched,
            daily_by_ticker=daily_by_ticker,
            sector_map=sector_map,
            market_period_returns=market_period_returns,
        )
        enriched = PersistenceEngine(cfg).enrich(
            enriched,
            daily_by_ticker=daily_by_ticker,
            history=history,
        )
        enriched = EmergingLeaderEngine(cfg).enrich(
            enriched,
            history=history,
            market_period_returns=market_period_returns,
        )
        # Exhaustion Risk V1 is observational. It is calculated before
        # lifecycle assignment but does not feed back into lifecycle yet.
        enriched = ExhaustionRiskEngine(cfg).enrich(
            enriched,
            daily_by_ticker=daily_by_ticker,
            history=history,
        )

    finalized = analyzer.finalize(enriched)
    lifecycle = lifecycle_engine or LeaderLifecycleEngine(cfg)
    finalized = lifecycle.enrich(finalized, daily_by_ticker=daily_by_ticker)
    return resolved, finalized
