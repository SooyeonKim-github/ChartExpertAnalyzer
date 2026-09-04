from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class CollectionResult:
    source_id: str
    endpoint_id: str
    discovered: int = 0
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    duplicated: int = 0
    skipped: int = 0
    failed: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    run_id: str | None = None
    health_status: str = "UNKNOWN"
    consecutive_failures: int = 0
    checkpoint_value: str | None = None
    errors: List[str] = field(default_factory=list)
