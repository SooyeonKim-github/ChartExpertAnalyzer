from __future__ import annotations

import numpy as np
import pandas as pd


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename = {}
    for col in out.columns:
        lc = str(col).lower()
        if lc in {"open", "시가"}: rename[col] = "open"
        elif lc in {"high", "고가"}: rename[col] = "high"
        elif lc in {"low", "저가"}: rename[col] = "low"
        elif lc in {"close", "종가"}: rename[col] = "close"
        elif lc in {"volume", "거래량"}: rename[col] = "volume"
        elif lc in {"value", "거래대금"}: rename[col] = "value"
    out = out.rename(columns=rename)
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"OHLCV columns missing: {missing}")
    out = out.sort_index()
    for c in required:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.dropna(subset=["open", "high", "low", "close"])


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = normalize_ohlcv(df)
    out["ma5"] = out["close"].rolling(5).mean()
    out["ma20"] = out["close"].rolling(20).mean()
    out["ma60"] = out["close"].rolling(60).mean()
    out["vol_ma20"] = out["volume"].rolling(20).mean()
    delta = out["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi14"] = 100 - 100 / (1 + rs)
    prev_close = out["close"].shift(1)
    tr = pd.concat([out["high"] - out["low"], (out["high"] - prev_close).abs(), (out["low"] - prev_close).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    return out
