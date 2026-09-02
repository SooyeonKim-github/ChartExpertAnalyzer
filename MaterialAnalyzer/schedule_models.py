from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1

from .models import canonical_url, clean_text


@dataclass
class ScheduleItem:
    collected_at: str
    published_at: str
    event_date: str
    event_time: str
    schedule_kind: str
    confidence: float
    source: str
    source_type: str
    title: str
    summary: str
    url: str
    query: str = ""
    category: str = ""
    date_evidence: str = ""

    def __post_init__(self) -> None:
        self.title = clean_text(self.title)
        self.summary = clean_text(self.summary)
        self.url = canonical_url(self.url)
        self.query = clean_text(self.query)
        self.category = clean_text(self.category)
        self.schedule_kind = clean_text(self.schedule_kind)
        self.event_date = clean_text(self.event_date)
        self.event_time = clean_text(self.event_time)
        self.date_evidence = clean_text(self.date_evidence)
        self.confidence = round(max(0.0, min(float(self.confidence), 1.0)), 3)

    @property
    def dedup_key(self) -> str:
        seed = "|".join(
            [
                self.event_date,
                self.event_time,
                self.url,
                self.schedule_kind,
                self.title.lower(),
            ]
        )
        return sha1(seed.encode("utf-8", errors="ignore")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        row = asdict(self)
        row["dedup_key"] = self.dedup_key
        return row
