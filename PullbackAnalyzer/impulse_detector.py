from __future__ import annotations

import numpy as np
import pandas as pd

from config import PullbackConfig
from models import ImpulseContext


def _event_candidates(d: pd.DataFrame, cfg: PullbackConfig) -> list[dict]:
    n = len(d)
    start = max(cfg.impulse_breakout_lookback + 1, n - cfg.impulse_search_bars)
    end = n - cfg.impulse_min_age_bars
    candidates: list[dict] = []
    for pos in range(start, end):
        row = d.iloc[pos]
        if not (float(row["Close"]) > float(row["Open"])):
            continue
        base_start = max(0, pos - cfg.impulse_base_lookback)
        prior = d.iloc[base_start:pos]
        if prior.empty:
            continue
        base_pos_local = int(np.nanargmin(prior["Low"].to_numpy(dtype=float)))
        base_pos = base_start + base_pos_local
        base_price = float(d["Low"].iloc[base_pos])
        if base_price <= 0:
            continue
        ret = (float(row["High"]) / base_price - 1.0) * 100.0
        vr = float(row["Volume_Ratio_20"]) if pd.notna(row["Volume_Ratio_20"]) else 0.0
        body_atr = float(row["Body_ATR"]) if pd.notna(row["Body_ATR"]) else 0.0
        prior_high = float(d["High"].iloc[max(0, pos-cfg.impulse_breakout_lookback):pos].max())
        breakout = float(row["Close"]) > prior_high
        if ret < cfg.impulse_min_return_pct:
            continue
        if vr < cfg.impulse_volume_ratio_min and body_atr < cfg.impulse_body_atr_min and not breakout:
            continue
        strength = (
            min(ret / cfg.impulse_strong_return_pct, 2.0)
            + min(vr / max(cfg.impulse_volume_ratio_strong, 0.01), 2.0)
            + min(body_atr, 2.0)
            + (1.0 if breakout else 0.0)
        )
        candidates.append({
            "pos": pos, "base_pos": base_pos, "base_price": base_price, "ret": ret,
            "vr": vr, "body_atr": body_atr, "breakout": breakout,
            "prior_high": prior_high, "strength": strength,
        })
    return candidates


def detect_impulse(d: pd.DataFrame, cfg: PullbackConfig) -> ImpulseContext:
    candidates = _event_candidates(d, cfg)
    if not candidates:
        return ImpulseContext()

    selected = max(candidates, key=lambda x: (x["pos"], x["strength"]))
    distinct: list[dict] = []
    for item in candidates:
        if not distinct or item["pos"] - distinct[-1]["pos"] >= cfg.impulse_event_separation_bars:
            distinct.append(item)
        elif item["strength"] > distinct[-1]["strength"]:
            distinct[-1] = item
    sequence = 1
    for i, item in enumerate(distinct, 1):
        if item["pos"] <= selected["pos"]:
            sequence = i

    pos = selected["pos"]
    base_pos = selected["base_pos"]
    return ImpulseContext(
        available=True,
        bar_pos=pos,
        date=d.index[pos].strftime("%Y-%m-%d"),
        base_pos=base_pos,
        base_date=d.index[base_pos].strftime("%Y-%m-%d"),
        base_price=selected["base_price"],
        open_price=float(d["Open"].iloc[pos]),
        high_price=float(d["High"].iloc[pos]),
        close_price=float(d["Close"].iloc[pos]),
        return_pct=selected["ret"],
        volume_ratio=selected["vr"],
        body_atr=selected["body_atr"],
        breakout_level=selected["prior_high"],
        breakout=bool(selected["breakout"]),
        event_count=len(distinct),
        sequence=sequence,
    )
