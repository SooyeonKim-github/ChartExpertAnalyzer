from __future__ import annotations

import pandas as pd

from .data import TrendFollowingDataProvider
from .indicators import add_moving_average_indicators
from .models import StageScreenResult
from .regime import (
    add_stage_labels,
    classify_market_regime,
    compute_52w_breadth_history,
    compute_intraday_strength_history,
    latest_breadth_snapshot,
    latest_intraday_snapshot,
)
from .strength import add_cross_sectional_rs_percentiles, compute_relative_strength_snapshot
from .structure import (
    BASE_DETECTED,
    compute_generic_base_snapshot,
    compute_prior_advance_snapshot,
    link_prior_advance_to_base,
)


def _optional_float(value):
    return None if value is None or pd.isna(value) else float(value)


def _build_market_context(provider, cfg, resolved):
    mcfg = cfg["market_regime"]
    bcfg = mcfg.get("breadth_52w", {})
    icfg = mcfg.get("intraday_strength", {})
    regimes = {}
    breadths = {}
    intradays = {}

    for market in ("KOSPI", "KOSDAQ"):
        try:
            index_df = provider.get_market_index(market, resolved)
        except Exception as exc:
            print(f"[WARN] {market} market regime index load failed: {exc}")
            index_df = pd.DataFrame(columns=["open", "high", "low", "close"])

        regimes[market] = classify_market_regime(
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
            if not bool(icfg.get("enabled", True)):
                raise RuntimeError("intraday-strength proxy disabled")
            history = compute_intraday_strength_history(
                index_df,
                strong_clv_threshold=float(icfg.get("strong_clv_threshold", 0.70)),
                weak_clv_threshold=float(icfg.get("weak_clv_threshold", 0.30)),
                short_window=int(icfg.get("short_window", 5)),
                long_window=int(icfg.get("long_window", 20)),
            )
            intradays[market] = latest_intraday_snapshot(
                history,
                market=market,
                short_window=int(icfg.get("short_window", 5)),
                long_window=int(icfg.get("long_window", 20)),
            )
        except Exception as exc:
            print(f"[WARN] {market} intraday-strength proxy failed: {exc}")
            intradays[market] = latest_intraday_snapshot(
                pd.DataFrame(),
                market=market,
                short_window=int(icfg.get("short_window", 5)),
                long_window=int(icfg.get("long_window", 20)),
            )

        try:
            source, meta = provider.get_market_breadth_source(market, resolved)
            history = compute_52w_breadth_history(
                source,
                lookback_sessions=int(bcfg.get("lookback_sessions", 252)),
                min_history_sessions=int(bcfg.get("min_history_sessions", 252)),
                short_window=int(bcfg.get("short_window", 5)),
                long_window=int(bcfg.get("long_window", 20)),
            )
            breadths[market] = latest_breadth_snapshot(
                history,
                market=market,
                min_coverage_ratio=float(bcfg.get("min_coverage_ratio", 0.60)),
                snapshot_dates_loaded=int(meta.get("loaded_dates", 0)),
                snapshot_dates_expected=int(meta.get("expected_dates", 0)),
                source_mode=str(meta.get("source_mode", "UNKNOWN")),
                membership_mode=str(meta.get("membership_mode", "UNKNOWN")),
                source_ticker_count=int(meta.get("ticker_count", 0)),
                failed_tickers=int(meta.get("failed_tickers", 0)),
            )
        except Exception as exc:
            print(f"[WARN] {market} 52W breadth analysis failed: {exc}")
            breadths[market] = latest_breadth_snapshot(
                pd.DataFrame(),
                market=market,
                min_coverage_ratio=float(bcfg.get("min_coverage_ratio", 0.60)),
            )

    return regimes, breadths, intradays


def _build_rs_context(provider, cfg, resolved, universe):
    rcfg = cfg.get("relative_strength", {})
    short_window = int(rcfg.get("short_window", 20))
    long_window = int(rcfg.get("long_window", 60))
    min_percentile = float(rcfg.get("experimental_min_percentile", 80.0))
    snapshots = {}
    rows = []

    for ticker, info in universe.iterrows():
        code = str(ticker).zfill(6)
        market = str(info.get("market", "")).upper()
        try:
            if not bool(rcfg.get("enabled", True)):
                raise RuntimeError("relative-strength analysis disabled")
            snap = compute_relative_strength_snapshot(
                provider.get_daily(code, resolved),
                provider.get_market_index(market, resolved),
                market=market,
                short_window=short_window,
                long_window=long_window,
                as_of=resolved,
            )
        except Exception as exc:
            print(f"[WARN] {code} relative-strength analysis failed: {exc}")
            snap = compute_relative_strength_snapshot(
                pd.DataFrame(columns=["close"]),
                pd.DataFrame(columns=["close"]),
                market=market,
                short_window=short_window,
                long_window=long_window,
                as_of=resolved,
            )
        snapshots[code] = snap
        rows.append(
            {
                "ticker": code,
                "market": market,
                "rs_20d_pct": snap.rs_20d_pct,
                "rs_60d_pct": snap.rs_60d_pct,
            }
        )

    ranks = {}
    if rows:
        ranked = add_cross_sectional_rs_percentiles(pd.DataFrame(rows))
        for _, row in ranked.iterrows():
            p20 = _optional_float(row.get("rs_percentile_20d"))
            p60 = _optional_float(row.get("rs_percentile_60d"))
            composite = _optional_float(row.get("rs_percentile_composite"))
            ranks[str(row["ticker"]).zfill(6)] = {
                "rs_percentile_20d": p20,
                "rs_percentile_60d": p60,
                "rs_percentile_composite": composite,
                "rs_experimental_percentile_pass": bool(
                    composite is not None and composite >= min_percentile
                ),
            }
    return snapshots, ranks


def screen_date(cfg, *, scan_date=None, top_n=None, base_dir, universe_xlsx=None):
    provider = TrendFollowingDataProvider(
        cfg,
        base_dir=base_dir,
        universe_xlsx=universe_xlsx,
    )
    resolved = provider.resolve_scan_date(scan_date)
    universe = provider.build_universe(resolved, top_n=top_n)
    markets, breadths, intradays = _build_market_context(provider, cfg, resolved)
    rs_snapshots, rs_ranks = _build_rs_context(provider, cfg, resolved, universe)

    trend_cfg = cfg["trend"]
    prior_cfg = cfg.get("prior_advance", {})
    base_cfg = cfg.get("base", {})
    results = []

    for ticker, info in universe.iterrows():
        try:
            code = str(ticker).zfill(6)
            daily = provider.get_daily(code, resolved)
            if daily.empty:
                continue

            enriched = add_moving_average_indicators(
                daily,
                ma_short=int(trend_cfg.get("ma_short", 50)),
                ma_long=int(trend_cfg.get("ma_long", 150)),
                slope_lookback=int(trend_cfg.get("slope_lookback", 20)),
            )
            enriched = add_stage_labels(
                enriched,
                slope_threshold_pct=float(
                    trend_cfg.get("experimental_slope_threshold_pct", 0.30)
                ),
            )
            last = enriched.iloc[-1]

            if bool(base_cfg.get("enabled", True)):
                base = compute_generic_base_snapshot(
                    enriched,
                    min_base_sessions=int(base_cfg.get("min_base_sessions", 15)),
                    max_base_sessions=int(base_cfg.get("max_base_sessions", 60)),
                    experimental_max_depth_pct=float(
                        base_cfg.get("experimental_max_depth_pct", 35.0)
                    ),
                    experimental_max_end_drawdown_pct=float(
                        base_cfg.get("experimental_max_end_drawdown_pct", 12.0)
                    ),
                    experimental_resistance_tolerance_pct=float(
                        base_cfg.get("experimental_resistance_tolerance_pct", 3.0)
                    ),
                    experimental_loose_ratio=float(
                        base_cfg.get("experimental_loose_ratio", 1.25)
                    ),
                    as_of=resolved,
                )
            else:
                base = compute_generic_base_snapshot(
                    pd.DataFrame(columns=["close"]),
                    as_of=resolved,
                )

            base_anchor = base.base_start_date if base.status == BASE_DETECTED else None
            prior = compute_prior_advance_snapshot(
                enriched
                if bool(prior_cfg.get("enabled", True))
                else pd.DataFrame(columns=["close", "ma150"]),
                lookback_sessions=int(prior_cfg.get("lookback_sessions", 120)),
                recent_window_sessions=int(prior_cfg.get("recent_window_sessions", 20)),
                experimental_min_advance_pct=float(
                    prior_cfg.get("experimental_min_advance_pct", 30.0)
                ),
                as_of=resolved,
                anchor_date=base_anchor,
            )
            advance_base = link_prior_advance_to_base(
                base,
                prior_low=prior.prior_low,
                prior_peak=prior.prior_peak,
                peak_to_base_sessions=prior.sessions_from_peak_to_anchor,
                current_close=_optional_float(last.get("close")),
            )

            market = str(info.get("market", "")).upper()
            market_snap = markets.get(market)
            breadth = breadths.get(market)
            intraday = intradays.get(market)
            rs = rs_snapshots.get(code)
            rs_rank = rs_ranks.get(code, {})
            if market_snap is None or breadth is None or intraday is None or rs is None:
                continue

            stage_core = bool(last["stage_core_pass"])
            market_core = bool(market_snap.market_eligible)
            lecture_core = stage_core and market_core

            results.append(
                StageScreenResult(
                    scan_date=resolved,
                    ticker=code,
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
                    stage_core_pass=stage_core,
                    stage_experimental_slope_pass=bool(last["stage_experimental_slope_pass"]),
                    stage_reason=str(last["stage_reason"]),
                    market_regime=market_snap.regime,
                    market_eligible=market_core,
                    market_index_close=market_snap.index_close,
                    market_index_ma50=market_snap.index_ma50,
                    market_index_ma150=market_snap.index_ma150,
                    market_index_ma150_slope_pct=market_snap.index_ma150_slope_pct,
                    market_index_close_vs_ma150_pct=market_snap.index_close_vs_ma150_pct,
                    market_index_ma50_vs_ma150_pct=market_snap.index_ma50_vs_ma150_pct,
                    market_lecture_ma150_position_pass=market_snap.lecture_ma150_position_pass,
                    market_lecture_ma150_slope_pass=market_snap.lecture_ma150_slope_pass,
                    market_experimental_slope_threshold_pass=market_snap.experimental_slope_threshold_pass,
                    market_experimental_ma50_alignment_pass=market_snap.experimental_ma50_alignment_pass,
                    market_regime_reason=market_snap.regime_reason,
                    market_breadth_status=breadth.status,
                    market_breadth_measurement=breadth.measurement,
                    market_breadth_source_mode=breadth.source_mode,
                    market_breadth_membership_mode=breadth.membership_mode,
                    market_breadth_source_ticker_count=breadth.source_ticker_count,
                    market_breadth_failed_tickers=breadth.failed_tickers,
                    market_breadth_universe_count=breadth.universe_count,
                    market_breadth_eligible_count=breadth.eligible_count,
                    market_breadth_coverage_ratio=breadth.coverage_ratio,
                    market_new_high_52w_count=breadth.new_high_52w_count,
                    market_new_low_52w_count=breadth.new_low_52w_count,
                    market_new_high_52w_ratio=breadth.new_high_52w_ratio,
                    market_new_low_52w_ratio=breadth.new_low_52w_ratio,
                    market_new_high_low_spread=breadth.new_high_low_spread,
                    market_breadth_5d_avg=breadth.breadth_5d_avg,
                    market_breadth_20d_avg=breadth.breadth_20d_avg,
                    market_breadth_5d_change=breadth.breadth_5d_change,
                    market_breadth_20d_change=breadth.breadth_20d_change,
                    market_breadth_direction=breadth.breadth_direction,
                    market_breadth_snapshot_dates_loaded=breadth.snapshot_dates_loaded,
                    market_breadth_snapshot_dates_expected=breadth.snapshot_dates_expected,
                    market_breadth_snapshot_date_coverage_ratio=breadth.snapshot_date_coverage_ratio,
                    market_breadth_filter_applied=False,
                    market_intraday_status=intraday.status,
                    market_intraday_measurement=intraday.measurement,
                    market_gap_return_pct=intraday.gap_return_pct,
                    market_open_close_return_pct=intraday.open_close_return_pct,
                    market_close_return_pct=intraday.close_return_pct,
                    market_close_location_value=intraday.close_location_value,
                    market_recovery_strength_pct=intraday.recovery_strength_pct,
                    market_fade_strength_pct=intraday.fade_strength_pct,
                    market_intraday_label=intraday.intraday_label,
                    market_experimental_intraday_strength_score=intraday.experimental_intraday_strength_score,
                    market_weak_open_strong_close_5d_ratio=intraday.weak_open_strong_close_5d_ratio,
                    market_weak_open_strong_close_20d_ratio=intraday.weak_open_strong_close_20d_ratio,
                    market_strong_open_weak_close_5d_ratio=intraday.strong_open_weak_close_5d_ratio,
                    market_strong_open_weak_close_20d_ratio=intraday.strong_open_weak_close_20d_ratio,
                    market_strong_close_5d_ratio=intraday.strong_close_5d_ratio,
                    market_strong_close_20d_ratio=intraday.strong_close_20d_ratio,
                    market_weak_close_5d_ratio=intraday.weak_close_5d_ratio,
                    market_weak_close_20d_ratio=intraday.weak_close_20d_ratio,
                    market_intraday_direction=intraday.intraday_direction,
                    market_intraday_filter_applied=False,
                    rs_status=rs.status,
                    rs_measurement=rs.measurement,
                    rs_percentile_scope=rs.percentile_scope,
                    stock_return_20d_pct=rs.stock_return_20d_pct,
                    benchmark_return_20d_pct=rs.benchmark_return_20d_pct,
                    rs_20d_pct=rs.rs_20d_pct,
                    stock_return_60d_pct=rs.stock_return_60d_pct,
                    benchmark_return_60d_pct=rs.benchmark_return_60d_pct,
                    rs_60d_pct=rs.rs_60d_pct,
                    rs_percentile_20d=rs_rank.get("rs_percentile_20d"),
                    rs_percentile_60d=rs_rank.get("rs_percentile_60d"),
                    rs_percentile_composite=rs_rank.get("rs_percentile_composite"),
                    rs_label=rs.rs_label,
                    rs_experimental_20d_outperform_pass=bool(
                        rs.rs_20d_pct is not None and rs.rs_20d_pct > 0
                    ),
                    rs_experimental_60d_outperform_pass=bool(
                        rs.rs_60d_pct is not None and rs.rs_60d_pct > 0
                    ),
                    rs_experimental_percentile_pass=bool(
                        rs_rank.get("rs_experimental_percentile_pass", False)
                    ),
                    rs_filter_applied=False,
                    base_status=base.status,
                    base_measurement=base.measurement,
                    base_start_date=base.base_start_date,
                    base_end_date=base.base_end_date,
                    base_duration_sessions=base.base_duration_sessions,
                    base_high_date=base.base_high_date,
                    base_high=base.base_high,
                    base_low_date=base.base_low_date,
                    base_low=base.base_low,
                    base_depth_pct=base.base_depth_pct,
                    base_current_vs_high_pct=base.current_vs_base_high_pct,
                    base_atr_early_pct=base.atr_early_pct,
                    base_atr_late_pct=base.atr_late_pct,
                    base_atr_contraction_ratio=base.atr_contraction_ratio,
                    base_range_early_pct=base.range_early_pct,
                    base_range_late_pct=base.range_late_pct,
                    base_range_contraction_ratio=base.range_contraction_ratio,
                    base_close_dispersion_pct=base.close_dispersion_pct,
                    base_experimental_quality_score=base.experimental_quality_score,
                    base_experimental_depth_pass=base.experimental_depth_pass,
                    base_experimental_end_near_high_pass=base.experimental_end_near_high_pass,
                    base_experimental_resistance_pass=base.experimental_resistance_pass,
                    base_filter_applied=False,
                    prior_advance_status=prior.status,
                    prior_advance_measurement=prior.measurement,
                    prior_advance_anchor_mode=prior.anchor_mode,
                    prior_advance_anchor_is_base=bool(base_anchor is not None),
                    prior_advance_lookback_sessions=prior.lookback_sessions,
                    prior_advance_recent_window_sessions=prior.recent_window_sessions,
                    prior_advance_low_date=prior.prior_low_date,
                    prior_advance_peak_date=prior.prior_peak_date,
                    prior_advance_low=prior.prior_low,
                    prior_advance_peak=prior.prior_peak,
                    prior_advance_pct=prior.prior_advance_pct,
                    prior_advance_duration_sessions=prior.prior_advance_duration_sessions,
                    prior_advance_sessions_from_peak_to_anchor=prior.sessions_from_peak_to_anchor,
                    prior_advance_peak_to_base_sessions=advance_base.peak_to_base_sessions,
                    prior_advance_current_vs_peak_pct=prior.current_vs_prior_peak_pct,
                    prior_advance_peak_vs_ma150_pct=prior.prior_peak_vs_ma150_pct,
                    prior_advance_drawdown_to_base_low_pct=advance_base.drawdown_from_prior_peak_to_base_low_pct,
                    prior_advance_retention_ratio=advance_base.advance_retention_ratio,
                    prior_advance_current_retention_ratio=advance_base.current_advance_retention_ratio,
                    prior_return_60d_pct=prior.return_60d_pct,
                    prior_return_120d_pct=prior.return_120d_pct,
                    prior_advance_experimental_min_pass=prior.experimental_min_advance_pass,
                    prior_advance_filter_applied=False,
                    lecture_core_pass=lecture_core,
                    experimental_filters_applied=False,
                )
            )
        except Exception as exc:
            print(f"[WARN] {ticker} trend analysis failed: {exc}")

    results.sort(
        key=lambda row: (
            0 if row.lecture_core_pass else 1,
            0 if row.stage == "STAGE_2" else 1,
            -(row.rs_percentile_composite or -1.0),
            row.trading_value_rank,
        )
    )
    return resolved, results
