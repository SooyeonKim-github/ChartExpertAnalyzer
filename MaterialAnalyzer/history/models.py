from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class HistoricalRangeConfig:
    requested_start: date
    requested_end: date
    warmup_days: int = 180
    chunk_days: int = 7
    government_max_pages: int = 500
    continue_on_error: bool = True

    @property
    def context_start(self) -> date:
        return self.requested_start - timedelta(days=max(0, int(self.warmup_days)))

    def validate(self) -> None:
        if self.requested_end < self.requested_start:
            raise ValueError("requested_end must be >= requested_start")
        if self.chunk_days < 1:
            raise ValueError("chunk_days must be >= 1")


@dataclass(frozen=True)
class RangeChunk:
    source_id: str
    start: date
    end: date

    @property
    def key(self) -> tuple[str, str, str]:
        return self.source_id, self.start.isoformat(), self.end.isoformat()
