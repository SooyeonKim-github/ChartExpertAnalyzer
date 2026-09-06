from __future__ import annotations

from datetime import date, timedelta

from .models import RangeChunk


def plan_chunks(source_id: str, start: date, end: date, chunk_days: int) -> list[RangeChunk]:
    if end < start:
        return []
    size = max(1, int(chunk_days))
    chunks: list[RangeChunk] = []
    current = start
    while current <= end:
        chunk_end = min(end, current + timedelta(days=size - 1))
        chunks.append(RangeChunk(source_id=source_id, start=current, end=chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks
