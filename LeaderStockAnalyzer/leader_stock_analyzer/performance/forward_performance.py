from __future__ import annotations

import math

import pandas as pd


def _finite(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


class ForwardPerformanceEngine:
    """Future-only range evaluator.

    This class must never be called from the same-day screening decision path.
    It exists only for range/backtest reporting and uses data strictly after the
    scan-date row when calculating future returns, MFE and MAE.
    """

    def __init__(self, cfg: dict):
        pcfg = cfg.get("performance", {})
        self.horizons = [int(x) for x in pcfg.get("horizons", [1, 5, 20, 60])]
        self.excursion_horizons = [int(x) for x in pcfg.get("excursion_horizons", [5, 20, 60])]
        self.breakout_hold_days = [int(x) for x in pcfg.get("breakout_hold_days", [1, 3])]
        self.breakout_hold_tolerance_pct = float(pcfg.get("breakout_hold_tolerance_pct", 2.0))

    @staticmethod
    def _prepare(daily: pd.DataFrame, scan_date: str) -> pd.DataFrame:
        if daily is None or daily.empty:
            return pd.DataFrame()
        df = daily.copy()
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[~df.index.isna()].sort_index()
        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                return pd.DataFrame()
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["high", "low", "close"])
        return df[df.index >= pd.Timestamp(scan_date)].copy()

    @staticmethod
    def _excursion(future: pd.DataFrame, entry: float, horizon: int) -> dict[str, float | int | None]:
        empty = {
            f"MFE_D{horizon}": None,
            f"MAE_D{horizon}": None,
            f"days_to_MFE_D{horizon}": None,
            f"days_to_MAE_D{horizon}": None,
        }
        if entry <= 0 or len(future) < horizon:
            return empty
        window = future.iloc[:horizon].copy().reset_index(drop=True)
        highs = pd.to_numeric(window["high"], errors="coerce")
        lows = pd.to_numeric(window["low"], errors="coerce")
        if highs.dropna().empty or lows.dropna().empty:
            return empty
        high_pos = int(highs.idxmax())
        low_pos = int(lows.idxmin())
        mfe = (float(highs.iloc[high_pos]) / entry - 1.0) * 100.0
        mae = (float(lows.iloc[low_pos]) / entry - 1.0) * 100.0
        return {
            f"MFE_D{horizon}": round(mfe, 3),
            f"MAE_D{horizon}": round(mae, 3),
            f"days_to_MFE_D{horizon}": high_pos + 1,
            f"days_to_MAE_D{horizon}": low_pos + 1,
        }

    def evaluate(
        self,
        daily: pd.DataFrame,
        scan_date: str,
        *,
        breakout_reference: float | None = None,
    ) -> dict[str, float | int | bool | None]:
        df = self._prepare(daily, scan_date)
        keys: dict[str, float | int | bool | None] = {}
        for h in self.horizons:
            keys[f"D+{h}"] = None
        for h in self.excursion_horizons:
            keys.update(self._excursion(pd.DataFrame(), 0.0, h))
        for d in self.breakout_hold_days:
            keys[f"breakout_hold_D{d}"] = None
        keys["failed_within_D3"] = None
        keys["mfe_capture_D20"] = None
        keys["excursion_ratio_D20"] = None

        if df.empty:
            return keys
        entry = _finite(df.iloc[0]["close"])
        if entry is None or entry <= 0:
            return keys

        future = df.iloc[1:].copy()
        for h in self.horizons:
            if len(future) >= h:
                close_h = _finite(future.iloc[h - 1]["close"])
                if close_h is not None:
                    keys[f"D+{h}"] = round((close_h / entry - 1.0) * 100.0, 3)

        for h in self.excursion_horizons:
            keys.update(self._excursion(future, entry, h))

        ref = _finite(breakout_reference)
        if ref is not None and ref > 0:
            floor = ref * (1.0 - self.breakout_hold_tolerance_pct / 100.0)
            for d in self.breakout_hold_days:
                if len(future) >= d:
                    closes = pd.to_numeric(future.iloc[:d]["close"], errors="coerce").dropna()
                    if len(closes) == d:
                        keys[f"breakout_hold_D{d}"] = bool((closes >= floor).all())
            if len(future) >= 3:
                closes3 = pd.to_numeric(future.iloc[:3]["close"], errors="coerce").dropna()
                if len(closes3) == 3:
                    keys["failed_within_D3"] = bool((closes3 < floor).any())

        d20 = _finite(keys.get("D+20"))
        mfe20 = _finite(keys.get("MFE_D20"))
        mae20 = _finite(keys.get("MAE_D20"))
        if d20 is not None and mfe20 is not None and mfe20 > 0:
            keys["mfe_capture_D20"] = round(d20 / mfe20, 4)
        if mfe20 is not None and mae20 is not None and abs(mae20) > 1e-9:
            keys["excursion_ratio_D20"] = round(mfe20 / abs(mae20), 4)

        return keys
