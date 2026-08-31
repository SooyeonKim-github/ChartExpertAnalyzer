from __future__ import annotations

"""Dynamic V2 range runner using the same KRX universe flow as KJB/Swing analyzers.

The original V1 remains in main_range.py.  Korean range execution now routes to
main_range_v2.py, while this wrapper still replaces only market/universe access so
execution does not depend on pykrx's fragile all-ticker snapshot endpoint.
"""

import sys
from pathlib import Path

import pandas as pd

import main_range_v2 as core


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
KJB_ROOT = PROJECT_ROOT / "KJBChartAnalyzer"
KJB_INFO_EXCEL = KJB_ROOT / "KOSPI_Info.xlsx"

if not KJB_ROOT.exists():
    raise RuntimeError(f"KJBChartAnalyzer folder not found: {KJB_ROOT}")
if not KJB_INFO_EXCEL.exists():
    raise RuntimeError(f"KOSPI_Info.xlsx not found: {KJB_INFO_EXCEL}")

# Reuse the exact universe implementation already used by KJBChartAnalyzer.
if str(KJB_ROOT) not in sys.path:
    sys.path.insert(0, str(KJB_ROOT))

from chartsel.universe.ticker_universe_service import TickerUniverseService  # noqa: E402


_UNIVERSE_SERVICE = TickerUniverseService(KJB_INFO_EXCEL)


def _latest_market_date_from_stock_series(
    _stock,
    requested: pd.Timestamp,
    max_lookback_days: int = 30,
) -> str:
    """Resolve the latest KRX date only from Samsung Electronics daily OHLCV.

    KJB/Swing use per-symbol date-range data instead of the all-ticker snapshot.
    Keep the same rule here so get_market_ohlcv_by_ticker() is never needed.
    """
    requested = min(
        pd.Timestamp(requested).normalize(),
        pd.Timestamp.today().normalize(),
    )
    start = requested - pd.Timedelta(days=max_lookback_days)

    try:
        cal = core.load_pykrx(
            "005930",
            start.strftime("%Y%m%d"),
            requested.strftime("%Y%m%d"),
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not resolve KRX trading date from 005930 daily OHLCV "
            f"at/before {requested.date()}: {type(exc).__name__}: {exc}"
        ) from exc

    if cal is None or cal.empty:
        raise RuntimeError(
            f"Could not resolve KRX trading date at/before {requested.date()}: "
            "005930 daily OHLCV is empty"
        )

    dates = pd.to_datetime(cal.index, errors="coerce")
    dates = dates[dates.notna()]
    dates = dates[dates.normalize() <= requested]
    if not len(dates):
        raise RuntimeError(
            f"Could not resolve KRX trading date at/before {requested.date()} "
            "from 005930 daily OHLCV"
        )
    return pd.Timestamp(dates.max()).strftime("%Y%m%d")


def _get_universe_from_kjb(
    snapshot_date: str,
    top_n: int,
    sort_by: str,
) -> pd.DataFrame:
    """Build Dynamic TOP-N with KJB's TickerUniverseService/KOSPI_Info.xlsx."""
    infos = _UNIVERSE_SERVICE.get_universe(
        top_n=top_n,
        sort_by=sort_by,
        include_etf=False,
    )
    if not infos:
        raise RuntimeError(
            f"KJB/Swing-style universe is empty: sort_by={sort_by}, top_n={top_n}"
        )

    rows = []
    for info in infos:
        rows.append({
            "ticker": info.ticker,
            "source_rank": info.source_rank,
            "name": info.name,
            "market": info.market,
            "market_cap": info.market_cap,
            "trading_value": info.trading_value,
            "volume": info.volume,
        })

    universe = pd.DataFrame(rows)
    print(
        f"[INFO] Universe source: {KJB_INFO_EXCEL} | "
        f"KJB TickerUniverseService | reference trading date={snapshot_date}"
    )
    print(
        "[INFO] Universe rule: current KOSPI_Info.xlsx snapshot; "
        "no pykrx all-ticker OHLCV/market-cap snapshot call"
    )
    return universe


# Keep Dynamic strategy state machine unchanged; replace only market access points.
core._latest_market_date = _latest_market_date_from_stock_series
core._get_universe = _get_universe_from_kjb


if __name__ == "__main__":
    raise SystemExit(core.run_range(core.build_parser().parse_args()))
