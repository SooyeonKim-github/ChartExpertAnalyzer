from __future__ import annotations

import math
import numpy as np
import pandas as pd

from config import StrategyConfig
from core.models import Channel, Pivot


def _line_values(slope: float, intercept: float, positions: np.ndarray) -> np.ndarray:
    return slope * positions + intercept


def build_best_rising_channel(df: pd.DataFrame, highs: list[Pivot], lows: list[Pivot], cfg: StrategyConfig) -> Channel | None:
    """영상의 '고점 2개 연결 → 같은 선을 아래 저점으로 복사'를 기계적으로 탐색한다."""
    n = len(df)
    start_floor = max(0, n - cfg.structure_lookback_bars)
    hs = [p for p in highs if p.pos >= start_floor][-7:]
    ls = [p for p in lows if p.pos >= start_floor]
    if len(hs) < 2 or not ls:
        return None

    best: tuple[float, Channel] | None = None
    closes = df["Close"].to_numpy(dtype=float)

    for a in range(len(hs)-1):
        for b in range(a+1, len(hs)):
            h1, h2 = hs[a], hs[b]
            gap = h2.pos - h1.pos
            if gap < cfg.channel_min_high_gap or gap > cfg.channel_max_high_gap:
                continue
            if h2.price <= h1.price:
                continue
            slope = (h2.price - h1.price) / gap
            if slope <= 0:
                continue
            upper_intercept = h1.price - slope * h1.pos
            candidate_lows = [p for p in ls if h1.pos < p.pos < n]
            if not candidate_lows:
                continue

            for low in candidate_lows:
                lower_intercept = low.price - slope * low.pos
                if lower_intercept >= upper_intercept:
                    continue
                upper_now = slope*(n-1) + upper_intercept
                lower_now = slope*(n-1) + lower_intercept
                width = upper_now - lower_now
                if lower_now <= 0 or width <= 0:
                    continue
                width_pct = width / lower_now
                if not (cfg.channel_min_width_pct <= width_pct <= cfg.channel_max_width_pct):
                    continue

                positions = np.arange(h1.pos, n)
                upper = _line_values(slope, upper_intercept, positions)
                lower = _line_values(slope, lower_intercept, positions)
                c = closes[h1.pos:n]
                tol = (upper-lower) * cfg.channel_cover_tolerance
                inside = (c >= lower-tol) & (c <= upper+tol)
                coverage = float(np.mean(inside)) if len(inside) else 0.0
                if coverage < cfg.channel_min_coverage:
                    continue

                high_touches = 0
                for p in hs:
                    if p.pos < h1.pos:
                        continue
                    w = (slope*p.pos + upper_intercept) - (slope*p.pos + lower_intercept)
                    if w > 0 and abs(p.price - (slope*p.pos + upper_intercept))/w <= cfg.channel_touch_tolerance:
                        high_touches += 1
                low_touches = 0
                for p in ls:
                    if p.pos < h1.pos:
                        continue
                    w = (slope*p.pos + upper_intercept) - (slope*p.pos + lower_intercept)
                    if w > 0 and abs(p.price - (slope*p.pos + lower_intercept))/w <= cfg.channel_touch_tolerance:
                        low_touches += 1

                channel = Channel(
                    high1_pos=h1.pos, high1_price=h1.price, high2_pos=h2.pos, high2_price=h2.price,
                    low_anchor_pos=low.pos, low_anchor_price=low.price, slope=slope,
                    upper_intercept=upper_intercept, lower_intercept=lower_intercept,
                    coverage=coverage, high_touches=high_touches, low_touches=low_touches,
                )
                # 최근 고점쌍, 높은 커버리지, 저점/고점 재접촉을 우선한다.
                recency = h2.pos / max(1, n-1)
                score = coverage*4 + min(high_touches, 3)*0.35 + min(low_touches, 3)*0.45 + recency
                if best is None or score > best[0]:
                    best = (score, channel)
    return best[1] if best else None


def channel_metrics(df: pd.DataFrame, channel: Channel, cfg: StrategyConfig) -> dict:
    n = len(df)
    pos = n - 1
    close = float(df["Close"].iloc[-1])
    upper, lower, mid = channel.upper(pos), channel.lower(pos), channel.mid(pos)
    position = channel.position(pos, close)
    start = max(channel.high1_pos, n - cfg.recent_lower_touch_bars)
    recent_positions = []
    for i in range(start, n):
        recent_positions.append(channel.position(i, float(df["Low"].iloc[i])))
    recent_min_position = float(np.nanmin(recent_positions)) if recent_positions else float("nan")
    breakdown = float(df["Low"].iloc[-1]) < lower*(1.0-cfg.stop_buffer_pct)
    return {
        "upper": upper, "lower": lower, "mid": mid, "position": position,
        "recent_min_position": recent_min_position,
        "near_lower": position <= cfg.cheap_zone_position,
        "recent_lower_touch": recent_min_position <= cfg.recent_lower_touch_position,
        "breakdown": breakdown,
        "room_to_mid_pct": (mid/close-1.0) if close else float("nan"),
        "room_to_upper_pct": (upper/close-1.0) if close else float("nan"),
    }
