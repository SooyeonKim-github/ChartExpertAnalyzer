from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import build_snapshot_universe, get_market_data_service, get_market_index_ohlcv  # noqa: E402
from ..indicators import add_moving_average_indicators
from ..regime import add_stage_labels, classify_market_regime
from ..structure.base_detector import BASE_DETECTED, compute_generic_base_snapshot
from ..structure.breakout import compute_breakout_snapshot
from ..structure.prior_advance import AVAILABLE as PRIOR_AVAILABLE, compute_prior_advance_snapshot
from ..structure.volume_contraction import compute_volume_contraction_snapshot

STRATEGY_FLAGS = (
    ("CORE", "strategy_core"),
    ("CORE_BASE", "strategy_core_base"),
    ("CORE_BASE_PRIOR", "strategy_core_base_prior"),
    ("CORE_BASE_VOLUME", "strategy_core_base_volume"),
    ("CORE_BASE_PRIOR_VOLUME", "strategy_core_base_prior_volume"),
    ("CORE_BREAKOUT", "strategy_core_breakout"),
    ("CORE_FULL_STACK", "strategy_core_full_stack"),
)


@dataclass(frozen=True)
class RangeRunMeta:
    range_start: str
    range_end: str
    top_n: int
    horizons: tuple[int, ...]
    calendar_dates: int
    universe_dates_loaded: int
    universe_dates_failed: int
    unique_tickers: int
    rows: int

    def to_dict(self) -> dict:
        return asdict(self)


def parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    value = str(text).strip().replace(" ", "").replace("～", "~")
    if "~" not in value:
        raise ValueError("날짜 범위는 YYYYMMDD~YYYYMMDD 형식이어야 합니다.")
    left, right = value.split("~", 1)
    start = pd.to_datetime(left, format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(right, format="%Y%m%d", errors="raise").normalize()
    if start > end:
        raise ValueError("시작일이 종료일보다 늦습니다.")
    return start, end


def _base_kwargs(cfg: dict) -> dict:
    c = cfg.get("base", {})
    return {
        "min_base_sessions": int(c.get("min_base_sessions", 15)),
        "max_base_sessions": int(c.get("max_base_sessions", 60)),
        "experimental_max_depth_pct": float(c.get("experimental_max_depth_pct", 35.0)),
        "experimental_max_end_drawdown_pct": float(c.get("experimental_max_end_drawdown_pct", 12.0)),
        "experimental_resistance_tolerance_pct": float(c.get("experimental_resistance_tolerance_pct", 3.0)),
        "experimental_loose_ratio": float(c.get("experimental_loose_ratio", 1.25)),
    }


def _prior_kwargs(cfg: dict) -> dict:
    c = cfg.get("prior_advance", {})
    return {
        "lookback_sessions": int(c.get("lookback_sessions", 120)),
        "recent_window_sessions": int(c.get("recent_window_sessions", 20)),
        "experimental_min_advance_pct": float(c.get("experimental_min_advance_pct", 30.0)),
    }


def _volume_kwargs(cfg: dict) -> dict:
    c = cfg.get("volume_contraction", {})
    return {
        "experimental_max_contraction_ratio": float(c.get("experimental_max_contraction_ratio", 0.80)),
        "experimental_max_down_vs_up_ratio": float(c.get("experimental_max_down_vs_up_ratio", 1.00)),
        "experimental_dry_up_volume_ratio": float(c.get("experimental_dry_up_volume_ratio", 0.70)),
        "experimental_min_dry_up_day_ratio": float(c.get("experimental_min_dry_up_day_ratio", 0.20)),
    }


def _breakout_kwargs(cfg: dict) -> dict:
    c = cfg.get("breakout", {})
    return {
        "experimental_min_close_breakout_pct": float(c.get("experimental_min_close_breakout_pct", 0.0)),
        "experimental_min_volume_ratio": float(c.get("experimental_min_volume_ratio", 1.50)),
        "experimental_near_breakout_pct": float(c.get("experimental_near_breakout_pct", 3.0)),
        "reference_volume_sessions": int(c.get("reference_volume_sessions", 20)),
    }


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    return out[~out.index.duplicated(keep="last")]


def _forward(full: pd.DataFrame, pos: int, horizons: tuple[int, ...]) -> dict:
    entry = float(full["close"].iloc[pos])
    out = {"entry_close": entry}
    for h in horizons:
        target = pos + h
        complete = target < len(full)
        out[f"forward_complete_D+{h}"] = bool(complete)
        out[f"forward_D+{h}_return_pct"] = (
            (float(full["close"].iloc[target]) / entry - 1.0) * 100.0
            if complete and entry > 0 else np.nan
        )
    max_h = max(horizons)
    future = full.iloc[pos + 1 : min(len(full), pos + max_h + 1)]
    if entry > 0 and not future.empty:
        out[f"MFE_{max_h}D_pct"] = (float(future["high"].max()) / entry - 1.0) * 100.0
        out[f"MAE_{max_h}D_pct"] = (float(future["low"].min()) / entry - 1.0) * 100.0
    return out


def summarize_strategy_buckets(results: pd.DataFrame, *, horizons: tuple[int, ...], strategy_flags=STRATEGY_FLAGS) -> pd.DataFrame:
    if results is None or results.empty:
        return pd.DataFrame()
    rows = []
    groups = [("ALL", results)] + [(str(m), g) for m, g in results.groupby("market", dropna=False)]
    for market, group in groups:
        for strategy, flag in strategy_flags:
            if flag not in group.columns:
                continue
            selected = group[group[flag].fillna(False).astype(bool)]
            for h in horizons:
                values = pd.to_numeric(selected.get(f"forward_D+{h}_return_pct"), errors="coerce").dropna()
                rows.append({
                    "market": market,
                    "strategy": strategy,
                    "horizon": f"D+{h}",
                    "signal_count": int(len(selected)),
                    "complete_count": int(len(values)),
                    "avg_return_pct": float(values.mean()) if len(values) else np.nan,
                    "median_return_pct": float(values.median()) if len(values) else np.nan,
                    "win_rate_pct": float((values > 0).mean() * 100.0) if len(values) else np.nan,
                    "std_return_pct": float(values.std(ddof=0)) if len(values) else np.nan,
                    "q25_return_pct": float(values.quantile(0.25)) if len(values) else np.nan,
                    "q75_return_pct": float(values.quantile(0.75)) if len(values) else np.nan,
                })
    return pd.DataFrame(rows)


def _build_universes(service, cfg: dict, dates: pd.DatetimeIndex, *, top_n: int, info_excel: str | Path):
    ucfg = cfg.get("universe", {})
    pool = max(top_n, top_n * max(1, int(ucfg.get("candidate_multiplier", 3))))
    frames, errors = [], []
    for i, dt in enumerate(dates, 1):
        day = pd.Timestamp(dt).normalize()
        try:
            snap, meta = build_snapshot_universe(
                day, top_n=pool, markets=("KOSPI", "KOSDAQ"), info_excel=info_excel,
                service=service, require_all_markets=True,
            )
            x = snap.copy()
            x["close"] = pd.to_numeric(x["close"], errors="coerce")
            x["trading_value"] = pd.to_numeric(x["trading_value"], errors="coerce")
            x = x[x["close"].fillna(0).ge(float(ucfg.get("min_price", 0))) & x["trading_value"].fillna(0).gt(0)]
            if bool(ucfg.get("exclude_spac", True)):
                x = x[~x["name"].astype(str).str.contains("스팩", na=False)]
            x = x.sort_values(["trading_value", "ticker"], ascending=[False, True]).head(top_n).reset_index(drop=True)
            x["trading_value_rank"] = range(1, len(x) + 1)
            x["scan_date"] = day
            x["universe_source_mode"] = str(meta.get("source_mode", "UNKNOWN"))
            x["universe_membership_mode"] = str(meta.get("membership_mode", "UNKNOWN"))
            frames.append(x)
        except Exception as exc:
            errors.append({"scan_date": day.strftime("%Y-%m-%d"), "stage": "UNIVERSE", "ticker": "", "error": f"{type(exc).__name__}: {exc}"})
        if i == 1 or i == len(dates) or i % 20 == 0:
            print(f"[RANGE] universe {i}/{len(dates)} loaded={len(frames)} failed={len(errors)}")
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), errors


def run_range_v1(cfg: dict, *, date_range: str, top_n: int, base_dir: str | Path, universe_xlsx: str | Path):
    start, end = parse_date_range(date_range)
    horizons = tuple(sorted({int(x) for x in cfg.get("backtest", {}).get("horizons", [5, 20, 60]) if int(x) > 0})) or (5, 20, 60)
    service = get_market_data_service()
    history_start = start - pd.Timedelta(days=max(520, int(cfg.get("data", {}).get("history_days", 520))))
    future_end = min(pd.Timestamp.today().normalize(), end + pd.Timedelta(days=max(horizons) * 2 + 30))

    index_cache = {
        market: _normalize(get_market_index_ohlcv(market, history_start, end, service=service))
        for market in ("KOSPI", "KOSDAQ")
    }
    dates = pd.DatetimeIndex(sorted({pd.Timestamp(d).normalize() for d in index_cache["KOSPI"].index if start <= pd.Timestamp(d).normalize() <= end}))
    if len(dates) == 0:
        raise RuntimeError("Range trading calendar is empty")

    universes, errors = _build_universes(service, cfg, dates, top_n=int(top_n), info_excel=universe_xlsx)
    if universes.empty:
        raise RuntimeError("No point-in-time universe dates were loaded")
    ticker_meta = universes.sort_values("scan_date").drop_duplicates("ticker", keep="last").set_index("ticker")[["name", "market"]]
    tickers = list(ticker_meta.index)

    full_cache, enriched_cache = {}, {}
    tcfg = cfg.get("trend", {})
    for i, ticker in enumerate(tickers, 1):
        meta = ticker_meta.loc[ticker]
        try:
            full = _normalize(service.get_ohlcv(ticker, history_start, future_end, market_hint=str(meta["market"]), allow_etf=False, fallback_yfinance=True))
            if full.empty:
                raise RuntimeError("empty OHLCV")
            full_cache[ticker] = full
            enriched = add_moving_average_indicators(full, ma_short=int(tcfg.get("ma_short", 50)), ma_long=int(tcfg.get("ma_long", 150)), slope_lookback=int(tcfg.get("slope_lookback", 20)))
            enriched_cache[ticker] = add_stage_labels(enriched, slope_threshold_pct=float(tcfg.get("experimental_slope_threshold_pct", 0.30)))
        except Exception as exc:
            errors.append({"scan_date": "", "stage": "HISTORY", "ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
        if i == 1 or i == len(tickers) or i % 50 == 0:
            print(f"[RANGE] history {i}/{len(tickers)} loaded={len(full_cache)}")

    mcfg = cfg.get("market_regime", {})
    regimes = {}
    for market, index_df in index_cache.items():
        for dt in dates:
            hist = index_df[index_df.index.normalize() <= dt]
            regimes[(market, dt)] = classify_market_regime(
                hist, market=market, ma_short=int(mcfg.get("ma_short", 50)), ma_long=int(mcfg.get("ma_long", 150)),
                slope_lookback=int(mcfg.get("slope_lookback", 20)),
                experimental_slope_threshold_pct=float(mcfg.get("experimental_slope_threshold_pct", 0.30)),
            )

    base_kw, prior_kw, volume_kw, breakout_kw = _base_kwargs(cfg), _prior_kwargs(cfg), _volume_kwargs(cfg), _breakout_kwargs(cfg)
    rows = []
    grouped = list(universes.groupby("scan_date", sort=True))
    for di, (scan_date, day) in enumerate(grouped, 1):
        dt = pd.Timestamp(scan_date).normalize()
        for _, candidate in day.iterrows():
            ticker, market = str(candidate["ticker"]).zfill(6), str(candidate["market"]).upper()
            full, enriched = full_cache.get(ticker), enriched_cache.get(ticker)
            if full is None or enriched is None:
                continue
            positions = np.flatnonzero(full.index.normalize() == dt)
            epositions = np.flatnonzero(enriched.index.normalize() == dt)
            if len(positions) == 0 or len(epositions) == 0:
                continue
            pos, epos = int(positions[-1]), int(epositions[-1])
            last = enriched.iloc[epos]
            regime = regimes.get((market, dt))
            core = bool(last.get("stage_core_pass", False) and regime is not None and regime.market_eligible)
            row = {
                "scan_date": dt.strftime("%Y-%m-%d"), "ticker": ticker, "name": str(candidate.get("name", ticker)),
                "market": market, "trading_value_rank": int(candidate.get("trading_value_rank", 0)),
                "trading_value": float(candidate.get("trading_value", 0.0) or 0.0),
                "universe_source_mode": candidate.get("universe_source_mode"), "universe_membership_mode": candidate.get("universe_membership_mode"),
                "close": float(last["close"]), "stage": str(last.get("stage", "")),
                "market_regime": None if regime is None else regime.regime, "lecture_core_pass": core,
                "strategy_core": core, "strategy_core_base": False, "strategy_core_base_prior": False,
                "strategy_core_base_volume": False, "strategy_core_base_prior_volume": False,
                "strategy_core_breakout": False, "strategy_core_full_stack": False,
                "base_status": "SKIPPED_NON_CORE", "prior_advance_status": "SKIPPED_NON_CORE",
                "volume_contraction_status": "SKIPPED_NON_CORE", "breakout_status": "SKIPPED_NON_CORE",
            }
            row.update(_forward(full, pos, horizons))

            if core:
                hist, ehist = full.iloc[:pos + 1].copy(), enriched.iloc[:epos + 1].copy()
                base = compute_generic_base_snapshot(hist, as_of=dt, **base_kw)
                anchor = base.base_start_date if base.status == BASE_DETECTED else None
                prior = compute_prior_advance_snapshot(ehist, as_of=dt, anchor_date=anchor, **prior_kw)
                volume = compute_volume_contraction_snapshot(hist, base_status=base.status, base_start_date=base.base_start_date, as_of=dt, exclude_last_session=True, **volume_kw)

                pre_hist, pre_ehist = full.iloc[:pos].copy(), enriched.iloc[:epos].copy()
                pre_base = compute_generic_base_snapshot(pre_hist, as_of=pre_hist.index[-1], **base_kw) if not pre_hist.empty else compute_generic_base_snapshot(pd.DataFrame(columns=["close"]))
                breakout = compute_breakout_snapshot(hist, pre_base_status=pre_base.status, pre_base_start_date=pre_base.base_start_date, as_of=dt, **breakout_kw)
                if pre_base.status == BASE_DETECTED and not pre_ehist.empty:
                    pre_prior = compute_prior_advance_snapshot(pre_ehist, as_of=pre_ehist.index[-1], anchor_date=pre_base.base_start_date, **prior_kw)
                    pre_volume = compute_volume_contraction_snapshot(hist, base_status=pre_base.status, base_start_date=pre_base.base_start_date, as_of=dt, exclude_last_session=True, **volume_kw)
                else:
                    pre_prior, pre_volume = None, None

                prior_pass = bool(prior.status == PRIOR_AVAILABLE and prior.experimental_min_advance_pass)
                volume_pass = bool(volume.experimental_contraction_pass)
                pre_prior_pass = bool(pre_prior is not None and pre_prior.status == PRIOR_AVAILABLE and pre_prior.experimental_min_advance_pass)
                pre_volume_pass = bool(pre_volume is not None and pre_volume.experimental_contraction_pass)
                breakout_pass = bool(breakout.experimental_signal_pass)
                row.update({
                    "base_status": base.status, "base_status_reason": base.status_reason, "base_start_date": base.base_start_date,
                    "base_duration_sessions": base.base_duration_sessions, "base_depth_pct": base.base_depth_pct,
                    "base_current_vs_high_pct": base.current_vs_base_high_pct, "base_atr_contraction_ratio": base.atr_contraction_ratio,
                    "base_range_contraction_ratio": base.range_contraction_ratio, "base_quality_score": base.experimental_quality_score,
                    "prior_advance_status": prior.status, "prior_advance_pct": prior.prior_advance_pct, "prior_advance_pass": prior_pass,
                    "volume_contraction_status": volume.status, "volume_contraction_ratio": volume.volume_contraction_ratio,
                    "volume_median_contraction_ratio": volume.volume_median_contraction_ratio, "volume_down_vs_up_ratio": volume.down_vs_up_volume_ratio,
                    "volume_dry_up_day_ratio": volume.dry_up_day_ratio, "volume_contraction_pass": volume_pass,
                    "breakout_prebase_status": pre_base.status, "breakout_prebase_start_date": pre_base.base_start_date,
                    "breakout_status": breakout.status, "breakout_level": breakout.breakout_level,
                    "breakout_close_pct": breakout.close_breakout_pct, "breakout_volume_ratio": breakout.breakout_volume_ratio,
                    "breakout_false_breakout": breakout.experimental_false_breakout, "breakout_signal_pass": breakout_pass,
                    "breakout_prebase_prior_pass": pre_prior_pass, "breakout_prebase_volume_pass": pre_volume_pass,
                    "strategy_core_base": base.status == BASE_DETECTED,
                    "strategy_core_base_prior": base.status == BASE_DETECTED and prior_pass,
                    "strategy_core_base_volume": base.status == BASE_DETECTED and volume_pass,
                    "strategy_core_base_prior_volume": base.status == BASE_DETECTED and prior_pass and volume_pass,
                    "strategy_core_breakout": pre_base.status == BASE_DETECTED and breakout_pass,
                    "strategy_core_full_stack": pre_base.status == BASE_DETECTED and pre_prior_pass and pre_volume_pass and breakout_pass,
                })
            rows.append(row)
        if di == 1 or di == len(grouped) or di % 20 == 0:
            print(f"[RANGE] analyze {di}/{len(grouped)} rows={len(rows):,}")

    results = pd.DataFrame(rows)
    summary = summarize_strategy_buckets(results, horizons=horizons)
    error_df = pd.DataFrame(errors)
    meta = RangeRunMeta(
        range_start=start.strftime("%Y-%m-%d"), range_end=end.strftime("%Y-%m-%d"), top_n=int(top_n), horizons=horizons,
        calendar_dates=int(len(dates)), universe_dates_loaded=int(universes["scan_date"].nunique()),
        universe_dates_failed=int(len({e.get("scan_date") for e in errors if e.get("stage") == "UNIVERSE"})),
        unique_tickers=int(len(tickers)), rows=int(len(results)),
    )
    return results, summary, error_df, meta
