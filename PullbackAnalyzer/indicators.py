from __future__ import annotations

import numpy as np
import pandas as pd

from config import PullbackConfig


def build_indicators(df: pd.DataFrame, cfg: PullbackConfig) -> pd.DataFrame:
    d = df.copy().sort_index()
    for p in cfg.ma_periods:
        d[f"MA{p}"] = d["Close"].rolling(p).mean()

    prev_close = d["Close"].shift(1)
    tr = pd.concat(
        [
            d["High"] - d["Low"],
            (d["High"] - prev_close).abs(),
            (d["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["ATR"] = tr.rolling(cfg.atr_period).mean()
    d["VMA20"] = d["Volume"].rolling(cfg.volume_period).mean()
    d["Volume_Ratio_20"] = d["Volume"] / d["VMA20"].replace(0, np.nan)

    mid = d["Close"].rolling(cfg.bb_period).mean()
    std = d["Close"].rolling(cfg.bb_period).std(ddof=0)
    d["BB_Mid"] = mid
    d["BB_Upper"] = mid + cfg.bb_std * std
    d["BB_Lower"] = mid - cfg.bb_std * std
    d["BB_Width_Pct"] = (d["BB_Upper"] - d["BB_Lower"]) / mid.replace(0, np.nan) * 100.0

    d["Body"] = (d["Close"] - d["Open"]).abs()
    d["Body_ATR"] = d["Body"] / d["ATR"].replace(0, np.nan)
    d["Range"] = d["High"] - d["Low"]
    d["Range_ATR"] = d["Range"] / d["ATR"].replace(0, np.nan)
    d["Close_Location"] = (d["Close"] - d["Low"]) / (d["High"] - d["Low"]).replace(0, np.nan)
    return d
