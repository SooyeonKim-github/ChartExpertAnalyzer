from __future__ import annotations

import numpy as np
import pandas as pd

from core.models import Pivot


def find_confirmed_pivots(df: pd.DataFrame, window: int = 3) -> tuple[list[Pivot], list[Pivot]]:
    """우측 window개 봉이 지나간 뒤에만 확정되는 pivot. 현재시점 미래값을 사용하지 않는다."""
    highs = df["High"].to_numpy(dtype=float)
    lows = df["Low"].to_numpy(dtype=float)
    ph: list[Pivot] = []
    pl: list[Pivot] = []
    n = len(df)
    for i in range(window, n - window):
        hseg = highs[i-window:i+window+1]
        lseg = lows[i-window:i+window+1]
        if np.isfinite(highs[i]) and highs[i] == np.nanmax(hseg) and np.sum(hseg == highs[i]) == 1:
            ph.append(Pivot(i, float(highs[i]), "HIGH"))
        if np.isfinite(lows[i]) and lows[i] == np.nanmin(lseg) and np.sum(lseg == lows[i]) == 1:
            pl.append(Pivot(i, float(lows[i]), "LOW"))
    return ph, pl
