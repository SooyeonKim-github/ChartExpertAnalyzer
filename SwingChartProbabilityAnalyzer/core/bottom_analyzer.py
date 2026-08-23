from __future__ import annotations

import numpy as np
import pandas as pd

from config import StrategyConfig
from core.models import Channel, Pivot


def add_moving_averages(df: pd.DataFrame, periods: tuple[int, ...]) -> pd.DataFrame:
    out = df.copy()
    for p in periods:
        out[f"MA{p}"] = out["Close"].rolling(p).mean()
    return out


def analyze_double_bottom(df: pd.DataFrame, lows: list[Pivot], channel: Channel, cfg: StrategyConfig) -> dict:
    """영상처럼 '추세 하단'에서 만들어진 쌍바닥/Higher-Low만 인정한다."""
    n = len(df)
    floor = max(0, n-cfg.double_bottom_lookback_bars)
    ls = [p for p in lows if p.pos >= floor]
    result = {"exists": False, "confirmed": False, "first": None, "second": None, "neckline": float("nan")}
    best = None
    for i in range(len(ls)-1):
        for j in range(i+1, len(ls)):
            a, b = ls[i], ls[j]
            gap = b.pos-a.pos
            if not (cfg.double_bottom_min_gap <= gap <= cfg.double_bottom_max_gap):
                continue
            # 두 바닥이 모두 채널 하단권이어야 한다.
            apos = channel.position(a.pos, a.price)
            bpos = channel.position(b.pos, b.price)
            if not (-0.20 <= apos <= 0.42 and -0.20 <= bpos <= 0.42):
                continue
            diff = abs(b.price-a.price)/a.price
            if diff > cfg.double_bottom_price_tolerance:
                continue
            if b.price < a.price*(1.0-cfg.higher_low_tolerance):
                continue
            neckline = float(df["High"].iloc[a.pos:b.pos+1].max())
            current = float(df["Close"].iloc[-1])
            confirmed = current > neckline
            recency = b.pos
            quality = (1.0-diff) + (0.4 if b.price >= a.price else 0.0) + (0.5 if confirmed else 0.0)
            key = (recency, quality)
            if best is None or key > best[0]:
                best = (key, a, b, neckline, confirmed)
    if best:
        _, a, b, neckline, confirmed = best
        result.update({"exists": True, "confirmed": confirmed, "first": a, "second": b, "neckline": neckline})
    return result


def analyze_moving_averages(df: pd.DataFrame, cfg: StrategyConfig) -> dict:
    x = add_moving_averages(df, cfg.ma_periods)
    current = x.iloc[-1]
    ma_cols = [f"MA{p}" for p in cfg.ma_periods]
    vals = [float(current[c]) for c in ma_cols if pd.notna(current[c])]
    if len(vals) != len(ma_cols):
        return {"clustered": False, "spread": float("nan"), "reclaimed": False, "ma5_hold": False, "data": x}
    close = float(current["Close"])
    spread = (max(vals)-min(vals))/close if close else float("nan")
    clustered = spread <= cfg.ma_cluster_max_spread
    current_top = max(vals)
    reclaimed = close > current_top
    if reclaimed:
        look = x.iloc[max(0, len(x)-1-cfg.ma_reclaim_lookback_bars):-1]
        if not look.empty:
            was_below = False
            for _, row in look.iterrows():
                rvals = [row[c] for c in ma_cols]
                if all(pd.notna(v) for v in rvals) and float(row["Close"]) <= max(map(float, rvals)):
                    was_below = True
                    break
            reclaimed = was_below
    ma5 = float(current.get("MA5", np.nan))
    ma5_hold = bool(np.isfinite(ma5) and float(current["Low"]) >= ma5*(1.0-cfg.ma5_hold_tolerance))
    return {"clustered": clustered, "spread": spread, "reclaimed": reclaimed, "ma5_hold": ma5_hold, "data": x}
