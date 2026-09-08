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


def _read_sector_snapshot(path: Path) -> dict[str, str]:
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig", dtype={"ticker": str})
    except Exception:
        return {}
    if not {"ticker", "sector"}.issubset(frame.columns):
        return {}
    ticker = frame["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    sector = frame["sector"].fillna("").astype(str).str.strip()
    valid = ticker.str.fullmatch(r"\d{6}", na=False) & sector.ne("")
    return dict(zip(ticker[valid], sector[valid]))


def _latest_prior_sector_snapshot(
    provider: PyKrxLeaderDataProvider,
    target: pd.Timestamp,
    max_staleness_days: int,
) -> tuple[pd.Timestamp | None, dict[str, str]]:
    """Load only a cached sector snapshot dated on/before target.

    This is deliberately backward-looking. A later snapshot is never used for a
    historical scan, so the fallback cannot introduce look-ahead membership.
    """
    root = getattr(provider, "sector_cache_root", None)
    if root is None:
        return None, {}
    root = Path(root)
    if not root.exists():
        return None, {}

    candidates: list[tuple[pd.Timestamp, Path]] = []
    for path in root.glob("*.csv"):
        try:
            dt = pd.Timestamp.strptime(path.stem, "%Y%m%d").normalize()
        except Exception:
            try:
                dt = pd.to_datetime(path.stem, format="%Y%m%d", errors="raise").normalize()
            except Exception:
                continue
        age = int((target - dt).days)
        if 0 <= age <= max_staleness_days:
            candidates.append((dt, path))

    for dt, path in sorted(candidates, key=lambda x: x[0], reverse=True):
        mapping = _read_sector_snapshot(path)
        if mapping:
            return dt, mapping
    return None, {}


def _sector_map_for_scan(
    provider: PyKrxLeaderDataProvider,
    resolved: str,
    cfg: dict,
) -> dict[str, str]:
    """Resolve sector membership once per month during a persistent Range scan.

    KRX sector membership is classification metadata, not a daily signal. Calling
    the KRX classification endpoint for every trading day caused long Range runs
    to lose sector context after repeated endpoint failures. We therefore refresh
    once per calendar month and reuse that point-in-time snapshot for the month.

    If the monthly refresh fails, only an earlier snapshot may be reused and only
    within the configured staleness window. Future snapshots are never used.
    """
    target = pd.Timestamp(resolved).normalize()
    month_key = target.strftime("%Y%m")
    scfg = cfg.get("sector_context", {})
    max_staleness_days = max(0, int(scfg.get("membership_max_staleness_days", 62)))

    cache = getattr(provider, "_leader_sector_month_cache", None)
    if not isinstance(cache, dict):
        cache = {}

    cached = cache.get(month_key)
    if isinstance(cached, dict) and cached.get("mapping"):
        return dict(cached["mapping"])

    fresh = provider.get_sector_map(resolved)
    if fresh:
        cache[month_key] = {
            "source_date": target,
            "mapping": dict(fresh),
            "fallback": False,
        }
        setattr(provider, "_leader_sector_month_cache", cache)
        return dict(fresh)

    # Prefer an already-used historical month from this same ascending Range run.
    prior_entries = []
    for entry in cache.values():
        if not isinstance(entry, dict) or not entry.get("mapping"):
            continue
        source = pd.to_datetime(entry.get("source_date"), errors="coerce")
        if pd.isna(source):
            continue
        source = pd.Timestamp(source).normalize()
        age = int((target - source).days)
        if 0 <= age <= max_staleness_days:
            prior_entries.append((source, entry))

    if prior_entries:
        source, entry = max(prior_entries, key=lambda x: x[0])
        mapping = dict(entry["mapping"])
        cache[month_key] = {
            "source_date": source,
            "mapping": mapping,
            "fallback": True,
        }
        setattr(provider, "_leader_sector_month_cache", cache)
        print(
            f"[WARN] Sector membership refresh failed for {resolved}; "
            f"using prior snapshot {source:%Y-%m-%d}"
        )
        return mapping

    # A previous run may already have a safe historical snapshot on disk.
    source, mapping = _latest_prior_sector_snapshot(
        provider,
        target,
        max_staleness_days,
    )
    if mapping and source is not None:
        cache[month_key] = {
            "source_date": source,
            "mapping": dict(mapping),
            "fallback": True,
        }
        setattr(provider, "_leader_sector_month_cache", cache)
        print(
            f"[WARN] Sector membership refresh failed for {resolved}; "
            f"using cached prior snapshot {source:%Y-%m-%d}"
        )
        return dict(mapping)

    cache[month_key] = {
        "source_date": target,
        "mapping": {},
        "fallback": False,
    }
    setattr(provider, "_leader_sector_month_cache", cache)
    print(f"[WARN] Sector membership unavailable for {resolved}; sector context disabled for this month")
    return {}


def screen_date(
    cfg: dict,
    *,
    scan_date: str | None = None,
    top_n: int | None = None,
    base_dir: str | Path,
    progress: bool = True,
    provider: PyKrxLeaderDataProvider | None = None,
    lifecycle_engine: LeaderLifecycleEngine | None = None,
    exhaustion_engine: ExhaustionRiskEngine | None = None,
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
        sector_map = _sector_map_for_scan(provider, resolved, cfg)
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
        # Exhaustion Risk V1.1 is observational. Range scans pass a persistent
        # engine so Leader Score / RS / Persistence peak-to-current decay uses
        # only previously observed scan dates without future leakage.
        exhaustion = exhaustion_engine or ExhaustionRiskEngine(cfg)
        enriched = exhaustion.enrich(
            enriched,
            daily_by_ticker=daily_by_ticker,
            history=history,
        )

    finalized = analyzer.finalize(enriched)
    lifecycle = lifecycle_engine or LeaderLifecycleEngine(cfg)
    finalized = lifecycle.enrich(finalized, daily_by_ticker=daily_by_ticker)
    return resolved, finalized
