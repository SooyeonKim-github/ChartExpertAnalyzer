from __future__ import annotations

from datetime import datetime, timezone, timedelta


KST = timezone(timedelta(hours=9), name="KST")


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def infer_published_precision(source_id: str, published_at: datetime | None, source_metadata: dict | None = None) -> str:
    if published_at is None:
        return "UNKNOWN"
    metadata = source_metadata or {}
    if source_id.upper() == "DART" and metadata.get("rcept_dt"):
        return "DATE"
    if published_at.hour == 0 and published_at.minute == 0 and published_at.second == 0 and metadata.get("date_only"):
        return "DATE"
    return "SECOND"
