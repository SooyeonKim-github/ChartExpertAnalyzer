from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "universe": {
        "top_n": 100,
        "min_price": 500,
        "exclude_spac": True,
        "market_cap_enabled": False,
        "market_cap_min": 50_000_000_000,
        "market_cap_max": 3_000_000_000_000,
    },
    "money_flow": {
        "daily_value_min": 60_000_000_000,
        "daily_value_mid": 30_000_000_000,
        "daily_value_low": 10_000_000_000,
        "intraday_3m_min": 5_000_000_000,
        "intraday_10m_min": 5_000_000_000,
    },
    "thresholds": {
        "strong_confirmed_leader": 85.0,
        "strong_confirmed_timing": 75.0,
        "confirmed_leader": 75.0,
        "confirmed_timing": 70.0,
        "watch_leader": 65.0,
        "max_confirmed_chase_risk": 60.0,
        "strong_rank_max": 5,
    },
    "weights": {
        "money_flow": 30.0,
        "price_strength": 20.0,
        "daily_position": 20.0,
        "intraday_strength": 15.0,
        "relative_strength": 10.0,
        "ma_structure": 5.0,
    },
    "sector_context": {
        "enabled": True,
        "min_members": 2,
        "strength_weights": {
            "rs_5d": 0.35,
            "rs_20d": 0.35,
            "turnover": 0.20,
            "breadth": 0.10,
        },
        "leader_weights": {
            "rs_20d": 0.50,
            "rs_5d": 0.25,
            "trading_value": 0.25,
        },
        "strong_sector_rank_max": 5,
        "strong_sector_leader_rank_max": 3,
        "weak_sector_rank_min": 15,
    },
    "persistence": {
        "enabled": True,
        "short_lookback": 5,
        "long_lookback": 10,
        "top_rank": 20,
        "broad_rank": 50,
        "strong_return_pct": 3.0,
        "high_score": 70.0,
        "medium_score": 45.0,
        "emerging_market_rank_max": 10,
        "emerging_min_leader_score": 85.0,
    },
    "data": {
        "history_days": 420,
        "intraday_root": "data/intraday",
        "cache_root": "cache",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        return deepcopy(DEFAULT_CONFIG)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return _deep_merge(DEFAULT_CONFIG, raw)
