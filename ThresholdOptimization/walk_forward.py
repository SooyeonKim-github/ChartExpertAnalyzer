from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_dates: tuple[pd.Timestamp, ...]
    validation_dates: tuple[pd.Timestamp, ...]
    purge_dates: tuple[pd.Timestamp, ...]

    @property
    def train_start(self) -> pd.Timestamp:
        return self.train_dates[0]

    @property
    def train_end(self) -> pd.Timestamp:
        return self.train_dates[-1]

    @property
    def validation_start(self) -> pd.Timestamp:
        return self.validation_dates[0]

    @property
    def validation_end(self) -> pd.Timestamp:
        return self.validation_dates[-1]


class PurgedWalkForwardSplitter:
    """Expanding-window walk-forward splitter with a trading-day purge gap.

    If D+20 is the target, a 20-trading-day gap prevents labels from the last
    training observations from reaching into the validation window.
    """

    def __init__(
        self,
        *,
        min_train_trading_days: int = 60,
        validation_trading_days: int = 40,
        step_trading_days: int = 40,
        purge_trading_days: int = 20,
    ) -> None:
        self.min_train = max(1, int(min_train_trading_days))
        self.validation = max(1, int(validation_trading_days))
        self.step = max(1, int(step_trading_days))
        self.purge = max(0, int(purge_trading_days))

    def split(self, dates) -> list[WalkForwardFold]:
        unique = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates), errors="coerce").dropna().unique()).sort_values()
        n = len(unique)
        folds: list[WalkForwardFold] = []
        train_end = self.min_train
        fold_id = 1
        while True:
            purge_start = train_end
            validation_start = purge_start + self.purge
            validation_end = validation_start + self.validation
            if validation_start >= n:
                break
            if validation_end > n:
                validation_end = n
            val_dates = tuple(pd.Timestamp(x) for x in unique[validation_start:validation_end])
            if not val_dates:
                break
            train_dates = tuple(pd.Timestamp(x) for x in unique[:train_end])
            purge_dates = tuple(pd.Timestamp(x) for x in unique[purge_start:validation_start])
            folds.append(WalkForwardFold(fold_id, train_dates, val_dates, purge_dates))
            if validation_end >= n:
                break
            train_end += self.step
            fold_id += 1
        return folds
