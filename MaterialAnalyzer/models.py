from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
import re
from urllib.parse import urlsplit, urlunsplit


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    text = _TAG_RE.sub(" ", value or "")
    return _SPACE_RE.sub(" ", text).strip()


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


@dataclass
class CollectedItem:
    collected_at: str
    published_at: str
    source_type: str
    source: str
    title: str
    summary: str
    url: str
    query: str = ""
    category: str = ""
    ticker: str = ""
    corp_code: str = ""
    report_code: str = ""
    future_hint: bool = False

    def __post_init__(self) -> None:
        self.title = clean_text(self.title)
        self.summary = clean_text(self.summary)
        self.url = canonical_url(self.url)
        self.query = clean_text(self.query)
        self.category = clean_text(self.category)

    @property
    def dedup_key(self) -> str:
        seed = self.url or f"{self.source}|{self.title.lower()}"
        return sha1(seed.encode("utf-8", errors="ignore")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        row = asdict(self)
        row["dedup_key"] = self.dedup_key
        return row
