from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..data import TrendFollowingDataProvider
from ..indicators import add_moving_average_indicators
from .base_detector import BASE_DETECTED, compute_generic_base_snapshot
from .breakout import compute_breakout_snapshot
from .prior_advance import compute_prior_advance_snapshot
from .volume_contraction import compute_volume_contraction_snapshot


def _base_kwargs(cfg: dict) -> dict:
    b = cfg.get("base", {})
    return {"min_base_sessions": int(b.get("min_base_sessions", 15)), "max_base_sessions": int(b.get("max_base_sessions", 60)), "experimental_max_depth_pct": float(b.get("experimental_max_depth_pct", 35.0)), "experimental_max_end_drawdown_pct": float(b.get("experimental_max_end_drawdown_pct", 12.0)), "experimental_resistance_tolerance_pct": float(b.get("experimental_resistance_tolerance_pct", 3.0)), "experimental_loose_ratio": float(b.get("experimental_loose_ratio", 1.25))}


def _volume_kwargs(cfg: dict) -> dict:
    v = cfg.get("volume_contraction", {})
    return {"experimental_max_contraction_ratio": float(v.get("experimental_max_contraction_ratio", 0.80)), "experimental_max_down_vs_up_ratio": float(v.get("experimental_max_down_vs_up_ratio", 1.00)), "experimental_dry_up_volume_ratio": float(v.get("experimental_dry_up_volume_ratio", 0.70)), "experimental_min_dry_up_day_ratio": float(v.get("experimental_min_dry_up_day_ratio", 0.20))}


def _breakout_kwargs(cfg: dict) -> dict:
    b = cfg.get("breakout", {})
    return {"experimental_min_close_breakout_pct": float(b.get("experimental_min_close_breakout_pct", 0.0)), "experimental_min_volume_ratio": float(b.get("experimental_min_volume_ratio", 1.50)), "experimental_near_breakout_pct": float(b.get("experimental_near_breakout_pct", 3.0)), "reference_volume_sessions": int(b.get("reference_volume_sessions", 20))}


def _prior_kwargs(cfg: dict) -> dict:
    p = cfg.get("prior_advance", {})
    return {"lookback_sessions": int(p.get("lookback_sessions", 120)), "recent_window_sessions": int(p.get("recent_window_sessions", 20)), "experimental_min_advance_pct": float(p.get("experimental_min_advance_pct", 30.0))}


def _bool(value) -> bool:
    return False if value is None or pd.isna(value) else bool(value)


def enrich_structure_features(df: pd.DataFrame, cfg: dict, *, resolved: str, base_dir: str | Path, universe_xlsx: str | Path | None = None) -> pd.DataFrame:
    """Append Phase 7.1/8/9 diagnostics to the single-date screen output."""
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    provider = TrendFollowingDataProvider(cfg, base_dir=base_dir, universe_xlsx=universe_xlsx)
    rows = []
    trend_cfg = cfg.get("trend", {})
    base_kwargs = _base_kwargs(cfg)
    volume_kwargs = _volume_kwargs(cfg)
    breakout_kwargs = _breakout_kwargs(cfg)
    prior_kwargs = _prior_kwargs(cfg)
    status_reasons = {"BASE_DETECTED":"depth/end/resistance conditions satisfied", "TOO_DEEP":"base depth exceeds experimental maximum", "TOO_FAR_FROM_HIGH":"current close is too far below base high", "TOO_LOOSE":"late base volatility/range expanded beyond loose threshold", "NO_RESISTANCE_ANCHOR":"base start is not near later resistance high", "NO_BASE":"no generic base candidate", "INSUFFICIENT":"insufficient history"}

    for _, src in df.iterrows():
        row = src.to_dict()
        code = str(row.get("ticker", "")).zfill(6)
        try:
            daily = provider.get_daily(code, resolved)
            daily.index = pd.to_datetime(daily.index, errors="coerce")
            daily = daily[~daily.index.isna()].sort_index()
            target = pd.Timestamp(resolved).normalize()
            daily = daily[daily.index.normalize() <= target].copy()
            row["base_status_reason"] = status_reasons.get(str(row.get("base_status")), "")
            atr_ratio = row.get("base_atr_contraction_ratio")
            range_ratio = row.get("base_range_contraction_ratio")
            row["base_experimental_atr_contraction_pass"] = bool(atr_ratio is not None and not pd.isna(atr_ratio) and float(atr_ratio) <= 1.0)
            row["base_experimental_range_contraction_pass"] = bool(range_ratio is not None and not pd.isna(range_ratio) and float(range_ratio) <= 1.0)

            volume = compute_volume_contraction_snapshot(daily, base_status=str(row.get("base_status", "")), base_start_date=row.get("base_start_date"), as_of=resolved, exclude_last_session=True, **volume_kwargs)
            for key, value in volume.to_dict().items():
                if key == "status": out_key = "volume_contraction_status"
                elif key == "measurement": out_key = "volume_contraction_measurement"
                elif key in {"base_start_date", "base_end_date", "sessions", "filter_applied"}: out_key = f"volume_contraction_{key}"
                elif key.startswith("volume_"): out_key = key
                else: out_key = f"volume_{key}"
                row[out_key] = value

            prior_day = daily[daily.index.normalize() < target].copy()
            if bool(cfg.get("base", {}).get("enabled", True)) and not prior_day.empty:
                pre_base = compute_generic_base_snapshot(prior_day, as_of=prior_day.index[-1], **base_kwargs)
            else:
                pre_base = compute_generic_base_snapshot(pd.DataFrame(columns=["close"]))
            breakout = compute_breakout_snapshot(daily, pre_base_status=pre_base.status, pre_base_start_date=pre_base.base_start_date, as_of=resolved, **breakout_kwargs)
            row["breakout_prebase_status"] = pre_base.status
            row["breakout_prebase_start_date"] = pre_base.base_start_date
            row["breakout_prebase_end_date"] = pre_base.base_end_date
            row["breakout_prebase_depth_pct"] = pre_base.base_depth_pct
            row["breakout_prebase_quality_score"] = pre_base.experimental_quality_score
            for key, value in breakout.to_dict().items():
                if key in {"status", "measurement", "base_start_date", "base_end_date", "filter_applied"}: out_key = f"breakout_{key}"
                elif key.startswith("breakout_"): out_key = key
                else: out_key = f"breakout_{key}"
                row[out_key] = value

            if pre_base.status == BASE_DETECTED and pre_base.base_start_date:
                enriched = add_moving_average_indicators(daily, ma_short=int(trend_cfg.get("ma_short", 50)), ma_long=int(trend_cfg.get("ma_long", 150)), slope_lookback=int(trend_cfg.get("slope_lookback", 20)))
                pre_prior = compute_prior_advance_snapshot(enriched, as_of=prior_day.index[-1] if not prior_day.empty else resolved, anchor_date=pre_base.base_start_date, **prior_kwargs)
                pre_volume = compute_volume_contraction_snapshot(daily, base_status=pre_base.status, base_start_date=pre_base.base_start_date, as_of=resolved, exclude_last_session=True, **volume_kwargs)
                row["breakout_prebase_prior_advance_pct"] = pre_prior.prior_advance_pct
                row["breakout_prebase_prior_pass"] = bool(pre_prior.experimental_min_advance_pass)
                row["breakout_prebase_volume_contraction_ratio"] = pre_volume.volume_contraction_ratio
                row["breakout_prebase_volume_pass"] = bool(pre_volume.experimental_contraction_pass)
            else:
                row["breakout_prebase_prior_advance_pct"] = None
                row["breakout_prebase_prior_pass"] = False
                row["breakout_prebase_volume_contraction_ratio"] = None
                row["breakout_prebase_volume_pass"] = False

            core = _bool(row.get("lecture_core_pass"))
            base_pass = str(row.get("base_status")) == BASE_DETECTED
            prior_pass = _bool(row.get("prior_advance_experimental_min_pass"))
            volume_pass = bool(volume.experimental_contraction_pass)
            breakout_pass = bool(breakout.experimental_signal_pass)
            row["experimental_stack_core_base_pass"] = core and base_pass
            row["experimental_stack_core_base_prior_pass"] = core and base_pass and prior_pass
            row["experimental_stack_core_base_volume_pass"] = core and base_pass and volume_pass
            row["experimental_stack_core_base_prior_volume_pass"] = core and base_pass and prior_pass and volume_pass
            row["experimental_stack_core_full_breakout_pass"] = bool(core and pre_base.status == BASE_DETECTED and row["breakout_prebase_prior_pass"] and row["breakout_prebase_volume_pass"] and breakout_pass)
        except Exception as exc:
            row["structure_enrichment_error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    return pd.DataFrame(rows)
