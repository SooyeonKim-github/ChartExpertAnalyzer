from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_dates: tuple[pd.Timestamp, ...]
    validation_dates: tuple[pd.Timestamp, ...]
    purge_dates: tuple[pd.Timestamp, ...]
    planned_validation_days: int

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

    @property
    def validation_fraction(self) -> float:
        if self.planned_validation_days <= 0:
            return 0.0
        return len(self.validation_dates) / self.planned_validation_days


class PurgedWalkForwardSplitter:
    """Expanding-window walk-forward splitter with a trading-day purge gap.

    If D+20 is the target, a 20-trading-day gap prevents labels from the last
    training observations from reaching into the validation window.

    A trailing partial validation window is included only when it contains at
    least ``min_validation_fraction`` of the configured validation length. This
    prevents tiny end-of-range folds (for example 2 days of a planned 40-day
    validation) from being treated as meaningful out-of-sample evidence.
    """

    def __init__(
        self,
        *,
        min_train_trading_days: int = 60,
        validation_trading_days: int = 40,
        step_trading_days: int = 40,
        purge_trading_days: int = 20,
        min_validation_fraction: float = 0.75,
    ) -> None:
        self.min_train = max(1, int(min_train_trading_days))
        self.validation = max(1, int(validation_trading_days))
        self.step = max(1, int(step_trading_days))
        self.purge = max(0, int(purge_trading_days))
        self.min_validation_fraction = min(1.0, max(0.0, float(min_validation_fraction)))
        self.min_validation_days = max(
            1,
            int(math.ceil(self.validation * self.min_validation_fraction)),
        )

    def split(self, dates) -> list[WalkForwardFold]:
        unique = pd.DatetimeIndex(
            pd.to_datetime(pd.Series(dates), errors="coerce").dropna().unique()
        ).sort_values()
        n = len(unique)
        folds: list[WalkForwardFold] = []
        train_end = self.min_train
        fold_id = 1

        while True:
            purge_start = train_end
            validation_start = purge_start + self.purge
            if validation_start >= n:
                break

            planned_validation_end = validation_start + self.validation
            validation_end = min(planned_validation_end, n)
            available_validation_days = validation_end - validation_start

            # Drop a tiny trailing partial fold rather than weakening the OOS
            # evidence with a window that is far shorter than configured.
            if available_validation_days < self.min_validation_days:
                break

            val_dates = tuple(
                pd.Timestamp(x) for x in unique[validation_start:validation_end]
            )
            if not val_dates:
                break

            train_dates = tuple(pd.Timestamp(x) for x in unique[:train_end])
            purge_dates = tuple(
                pd.Timestamp(x) for x in unique[purge_start:validation_start]
            )
            folds.append(
                WalkForwardFold(
                    fold_id=fold_id,
                    train_dates=train_dates,
                    validation_dates=val_dates,
                    purge_dates=purge_dates,
                    planned_validation_days=self.validation,
                )
            )

            if validation_end >= n:
                break
            train_end += self.step
            fold_id += 1

        return folds
