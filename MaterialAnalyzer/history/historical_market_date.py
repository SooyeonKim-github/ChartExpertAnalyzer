from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, time, timedelta

from MaterialAnalyzer.news.processing.normalization.datetime_normalizer import KST, normalize_datetime


class HistoricalMarketDateResolver:
    """Point-in-time KR market-date resolver backed by actual Samsung trading dates.

    DATE/UNKNOWN precision is conservatively shifted to the next trading session.
    Exact timestamps at or before 15:30 KST can affect the same trading session.
    """

    def __init__(self, start: date, end: date, market_close: time = time(15, 30)):
        self.market_close = market_close
        self._days = self._load_trading_days(start, end)
        self._ordinals = [d.toordinal() for d in self._days]

    @staticmethod
    def _load_trading_days(start: date, end: date) -> list[date]:
        padded_start = start - timedelta(days=14)
        padded_end = end + timedelta(days=14)
        try:
            from MarketData import get_market_data_service
            service = get_market_data_service()
            frame = service.get_ohlcv("005930", padded_start, padded_end, market_hint="KOSPI", allow_etf=False)
            days = sorted({ts.date() for ts in frame.index})
            if days:
                return days
        except Exception:
            pass
        # Conservative fallback: weekdays only. Coverage/reporting still makes the
        # absence of an exchange-backed calendar visible to the user.
        current = padded_start
        days: list[date] = []
        while current <= padded_end:
            if current.weekday() < 5:
                days.append(current)
            current += timedelta(days=1)
        return days

    def _next_trading_day(self, value: date, *, strictly_after: bool) -> date | None:
        target = value.toordinal()
        if not strictly_after and target in self._ordinals:
            return value
        idx = bisect_right(self._ordinals, target)
        return self._days[idx] if idx < len(self._days) else None

    def resolve_historical(self, published_at: datetime | None, precision: str | None) -> str | None:
        dt = normalize_datetime(published_at)
        if dt is None:
            return None
        precision = (precision or "UNKNOWN").upper()
        day = dt.date()
        exact = precision in {"SECOND", "MINUTE", "HOUR", "EXACT", "DATETIME"}
        if exact and day.toordinal() in self._ordinals and dt.timetz().replace(tzinfo=None) <= self.market_close:
            target = day
        else:
            target = self._next_trading_day(day, strictly_after=True)
        return target.strftime("%Y%m%d") if target else None

    def resolve(self, available_at: datetime | None) -> str | None:
        # Compatibility with ArticleNormalizer. HistoricalNormalizer calls the
        # precision-aware method after normalization.
        return self.resolve_historical(available_at, "SECOND")
