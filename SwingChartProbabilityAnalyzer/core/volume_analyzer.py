from __future__ import annotations

import numpy as np
import pandas as pd

from config import StrategyConfig
from core.models import Channel


def analyze_bottom_volume_and_reference(df: pd.DataFrame, channel: Channel, cfg: StrategyConfig) -> dict:
    x = df.copy()
    # 현재 거래량을 자기 평균에 포함시키면 급증비율이 희석되므로 직전 N일 평균과 비교한다.
    x["VolAvg"] = x["Volume"].shift(1).rolling(cfg.volume_avg_period).mean()
    x["VolRatio"] = x["Volume"] / x["VolAvg"].replace(0, np.nan)
    n = len(x)
    start = max(channel.high1_pos, n-cfg.reference_candle_lookback_bars)
    candidates = []
    for i in range(start, n):
        row = x.iloc[i]
        ratio = float(row["VolRatio"]) if pd.notna(row["VolRatio"]) else 0.0
        cpos = channel.position(i, float(row["Close"]))
        bullish = float(row["Close"]) > float(row["Open"])
        if ratio >= cfg.volume_surge_ratio and cpos <= cfg.cheap_zone_position and bullish:
            candidates.append((i, ratio, cpos))
    result = {
        "bottom_volume_surge": bool(candidates), "reference_pos": None, "reference_date": None,
        "reference_low": float("nan"), "reference_high": float("nan"), "reference_volume_ratio": float("nan"),
        "reference_low_held": False, "reference_high_break": False, "bullish_turn": False,
        "current_volume_ratio": float(x["VolRatio"].iloc[-1]) if pd.notna(x["VolRatio"].iloc[-1]) else float("nan"),
    }
    if not candidates:
        return result
    ref_pos, ratio, _ = candidates[-1]
    ref = x.iloc[ref_pos]
    ref_low = float(ref["Low"])
    ref_high = float(ref["High"])
    after = x.iloc[ref_pos+1:] if ref_pos+1 < n else x.iloc[0:0]
    min_after = float(after["Low"].min()) if not after.empty else ref_low
    held = min_after >= ref_low*(1.0-cfg.reference_low_tolerance)
    current_close = float(x["Close"].iloc[-1])
    high_break = current_close > ref_high
    bullish_turn = False
    if n >= 2:
        cur = x.iloc[-1]
        prev = x.iloc[-2]
        bullish_turn = held and float(cur["Close"]) > float(cur["Open"]) and float(cur["Close"]) > float(prev["Close"])
    result.update({
        "reference_pos": ref_pos, "reference_date": x.index[ref_pos].strftime("%Y-%m-%d"),
        "reference_low": ref_low, "reference_high": ref_high, "reference_volume_ratio": ratio,
        "reference_low_held": held, "reference_high_break": high_break, "bullish_turn": bullish_turn,
    })
    return result
