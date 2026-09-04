from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .datetime_normalizer import KST, normalize_datetime


class MarketDateResolver:
    """Resolve the date on which an article can first affect a regular KR session.

    V1 deliberately handles weekends only. Exchange holidays should be injected later
    through a trading-calendar provider instead of being hard-coded here.
    """

    def __init__(self, market_close: time = time(15, 30)):
        self.market_close = market_close

    @staticmethod
    def _next_weekday(value: date) -> date:
        current = value
        while current.weekday() >= 5:
            current += timedelta(days=1)
        return current

    def resolve(self, available_at: datetime | None) -> str | None:
        dt = normalize_datetime(available_at)
        if dt is None:
            return None
        target = dt.date()
        if target.weekday() >= 5:
            target = self._next_weekday(target)
        elif dt.timetz().replace(tzinfo=None) > self.market_close:
            target = self._next_weekday(target + timedelta(days=1))
        return target.strftime("%Y%m%d")
