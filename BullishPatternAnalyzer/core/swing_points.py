from __future__ import annotations

import numpy as np
import pandas as pd


def find_swing_highs(df: pd.DataFrame, order: int = 3) -> pd.DataFrame:
    values = df["high"].to_numpy(float)
    idx = []
    for i in range(order, len(values) - order):
        window = values[i - order : i + order + 1]
        if np.isfinite(values[i]) and values[i] == np.nanmax(window) and np.sum(window == values[i]) == 1:
            idx.append(i)
    return _points(df, idx, "high")


def find_swing_lows(df: pd.DataFrame, order: int = 3) -> pd.DataFrame:
    values = df["low"].to_numpy(float)
    idx = []
    for i in range(order, len(values) - order):
        window = values[i - order : i + order + 1]
        if np.isfinite(values[i]) and values[i] == np.nanmin(window) and np.sum(window == values[i]) == 1:
            idx.append(i)
    return _points(df, idx, "low")


def _points(df: pd.DataFrame, positions: list[int], price_col: str) -> pd.DataFrame:
    return pd.DataFrame([{"pos": pos, "date": df.index[pos], "price": float(df.iloc[pos][price_col])} for pos in positions], columns=["pos", "date", "price"])


def line_fit(points: pd.DataFrame) -> tuple[float, float]:
    if points is None or len(points) < 2:
        return float("nan"), float("nan")
    slope, intercept = np.polyfit(points["pos"].to_numpy(float), points["price"].to_numpy(float), 1)
    return float(slope), float(intercept)


def line_value(slope: float, intercept: float, pos: int) -> float:
    return float(slope * pos + intercept)
