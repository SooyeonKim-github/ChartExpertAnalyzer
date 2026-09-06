from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data import TrendFollowingDataProvider
from .indicators import add_moving_average_indicators
from .models import StageScreenResult
from .regime import add_stage_labels


def _optional_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def screen_date(
    cfg: dict,
    *,
    scan_date: str | None = None,
    top_n: int | None = None,
    base_dir: str | Path,
    universe_xlsx: str | Path | None = None,
) -> tuple[str, list[StageScreenResult]]:
    provider = TrendFollowingDataProvider(
        cfg,
        base_dir=base_dir,
        universe_xlsx=universe_xlsx,
    )
    resolved = provider.resolve_scan_date(scan_date)
    universe = provider.build_universe(resolved, top_n=top_n)

    tcfg = cfg["trend"]
    results: list[StageScreenResult] = []

    for ticker, info in universe.iterrows():
        try:
            daily = provider.get_daily(ticker, resolved)
            if daily.empty:
                continue

            enriched = add_moving_average_indicators(
                daily,
                ma_short=int(tcfg.get("ma_short", 50)),
                ma_long=int(tcfg.get("ma_long", 150)),
                slope_lookback=int(tcfg.get("slope_lookback", 20)),
            )
            enriched = add_stage_labels(
                enriched,
                slope_threshold_pct=float(tcfg.get("slope_threshold_pct", 0.30)),
            )
            last = enriched.iloc[-1]

            results.append(
                StageScreenResult(
                    scan_date=resolved,
                    ticker=str(ticker).zfill(6),
                    name=str(info.get("name", ticker)),
                    market=str(info.get("market", "")),
                    trading_value_rank=int(info.get("trading_value_rank", 0)),
                    close=float(last["close"]),
                    ma50=_optional_float(last.get("ma50")),
                    ma150=_optional_float(last.get("ma150")),
                    ma150_slope_pct=_optional_float(last.get("ma150_slope_pct")),
                    close_vs_ma150_pct=_optional_float(last.get("close_vs_ma150_pct")),
                    ma50_vs_ma150_pct=_optional_float(last.get("ma50_vs_ma150_pct")),
                    stage=str(last["stage"]),
                    trend_eligible=bool(last["trend_eligible"]),
                    stage_reason=str(last["stage_reason"]),
                )
            )
        except Exception as exc:
            print(f"[WARN] {ticker} stage analysis failed: {exc}")

    results.sort(
        key=lambda r: (
            0 if r.stage == "STAGE_2" else 1,
            r.trading_value_rank,
        )
    )
    return resolved, results
