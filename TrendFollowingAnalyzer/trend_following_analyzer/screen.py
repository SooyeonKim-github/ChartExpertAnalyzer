from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data import TrendFollowingDataProvider
from .indicators import add_moving_average_indicators
from .models import StageScreenResult
from .regime import (
    add_stage_labels,
    classify_market_regime,
    compute_52w_breadth_history,
    latest_breadth_snapshot,
)


def _optional_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _build_market_context(provider: TrendFollowingDataProvider, cfg: dict, resolved: str) -> tuple[dict, dict]:
    mcfg = cfg["market_regime"]
    bcfg = mcfg.get("breadth_52w", {})
    regime_snapshots = {}
    breadth_snapshots = {}

    for market in ("KOSPI", "KOSDAQ"):
        try:
            index_df = provider.get_market_index(market, resolved)
        except Exception as exc:
            print(f"[WARN] {market} market regime index load failed: {exc}")
            index_df = pd.DataFrame(columns=["close"])

        regime_snapshots[market] = classify_market_regime(
            index_df,
            market=market,
            ma_short=int(mcfg.get("ma_short", 50)),
            ma_long=int(mcfg.get("ma_long", 150)),
            slope_lookback=int(mcfg.get("slope_lookback", 20)),
            experimental_slope_threshold_pct=float(
                mcfg.get("experimental_slope_threshold_pct", 0.30)
            ),
        )

        try:
            source, meta = provider.get_market_breadth_source(market, resolved)
            breadth_history = compute_52w_breadth_history(
                source,
                lookback_sessions=int(bcfg.get("lookback_sessions", 252)),
                min_history_sessions=int(bcfg.get("min_history_sessions", 252)),
                short_window=int(bcfg.get("short_window", 5)),
                long_window=int(bcfg.get("long_window", 20)),
            )
            breadth_snapshots[market] = latest_breadth_snapshot(
                breadth_history,
                market=market,
                min_coverage_ratio=float(bcfg.get("min_coverage_ratio", 0.60)),
                snapshot_dates_loaded=int(meta.get("loaded_dates", 0)),
                snapshot_dates_expected=int(meta.get("expected_dates", 0)),
            )
        except Exception as exc:
            print(f"[WARN] {market} 52W breadth analysis failed: {exc}")
            breadth_snapshots[market] = latest_breadth_snapshot(
                pd.DataFrame(),
                market=market,
                min_coverage_ratio=float(bcfg.get("min_coverage_ratio", 0.60)),
            )

    return regime_snapshots, breadth_snapshots


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
    market_snapshots, breadth_snapshots = _build_market_context(provider, cfg, resolved)

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
                slope_threshold_pct=float(
                    tcfg.get("experimental_slope_threshold_pct", 0.30)
                ),
            )
            last = enriched.iloc[-1]

            market = str(info.get("market", "")).upper()
            market_snapshot = market_snapshots.get(market)
            breadth_snapshot = breadth_snapshots.get(market)
            if market_snapshot is None or breadth_snapshot is None:
                continue

            stage_core_pass = bool(last["stage_core_pass"])
            market_core_pass = bool(market_snapshot.market_eligible)
            # Phase 4B breadth is deliberately BACKTEST_ONLY. It does not gate this flag.
            lecture_core_pass = stage_core_pass and market_core_pass

            results.append(
                StageScreenResult(
                    scan_date=resolved,
                    ticker=str(ticker).zfill(6),
                    name=str(info.get("name", ticker)),
                    market=market,
                    trading_value_rank=int(info.get("trading_value_rank", 0)),
                    close=float(last["close"]),
                    ma50=_optional_float(last.get("ma50")),
                    ma150=_optional_float(last.get("ma150")),
                    ma150_slope_pct=_optional_float(last.get("ma150_slope_pct")),
                    close_vs_ma150_pct=_optional_float(last.get("close_vs_ma150_pct")),
                    ma50_vs_ma150_pct=_optional_float(last.get("ma50_vs_ma150_pct")),
                    stage=str(last["stage"]),
                    trend_eligible=bool(last["trend_eligible"]),
                    stage_core_pass=stage_core_pass,
                    stage_experimental_slope_pass=bool(
                        last["stage_experimental_slope_pass"]
                    ),
                    stage_reason=str(last["stage_reason"]),
                    market_regime=market_snapshot.regime,
                    market_eligible=market_core_pass,
                    market_index_close=market_snapshot.index_close,
                    market_index_ma50=market_snapshot.index_ma50,
                    market_index_ma150=market_snapshot.index_ma150,
                    market_index_ma150_slope_pct=market_snapshot.index_ma150_slope_pct,
                    market_index_close_vs_ma150_pct=market_snapshot.index_close_vs_ma150_pct,
                    market_index_ma50_vs_ma150_pct=market_snapshot.index_ma50_vs_ma150_pct,
                    market_lecture_ma150_position_pass=market_snapshot.lecture_ma150_position_pass,
                    market_lecture_ma150_slope_pass=market_snapshot.lecture_ma150_slope_pass,
                    market_experimental_slope_threshold_pass=market_snapshot.experimental_slope_threshold_pass,
                    market_experimental_ma50_alignment_pass=market_snapshot.experimental_ma50_alignment_pass,
                    market_regime_reason=market_snapshot.regime_reason,
                    market_breadth_status=breadth_snapshot.status,
                    market_breadth_measurement=breadth_snapshot.measurement,
                    market_breadth_universe_count=breadth_snapshot.universe_count,
                    market_breadth_eligible_count=breadth_snapshot.eligible_count,
                    market_breadth_coverage_ratio=breadth_snapshot.coverage_ratio,
                    market_new_high_52w_count=breadth_snapshot.new_high_52w_count,
                    market_new_low_52w_count=breadth_snapshot.new_low_52w_count,
                    market_new_high_52w_ratio=breadth_snapshot.new_high_52w_ratio,
                    market_new_low_52w_ratio=breadth_snapshot.new_low_52w_ratio,
                    market_new_high_low_spread=breadth_snapshot.new_high_low_spread,
                    market_breadth_5d_avg=breadth_snapshot.breadth_5d_avg,
                    market_breadth_20d_avg=breadth_snapshot.breadth_20d_avg,
                    market_breadth_5d_change=breadth_snapshot.breadth_5d_change,
                    market_breadth_20d_change=breadth_snapshot.breadth_20d_change,
                    market_breadth_direction=breadth_snapshot.breadth_direction,
                    market_breadth_snapshot_dates_loaded=breadth_snapshot.snapshot_dates_loaded,
                    market_breadth_snapshot_dates_expected=breadth_snapshot.snapshot_dates_expected,
                    market_breadth_snapshot_date_coverage_ratio=breadth_snapshot.snapshot_date_coverage_ratio,
                    market_breadth_filter_applied=False,
                    lecture_core_pass=lecture_core_pass,
                    experimental_filters_applied=False,
                )
            )
        except Exception as exc:
            print(f"[WARN] {ticker} trend analysis failed: {exc}")

    results.sort(
        key=lambda r: (
            0 if r.lecture_core_pass else 1,
            0 if r.stage == "STAGE_2" else 1,
            r.trading_value_rank,
        )
    )
    return resolved, results
