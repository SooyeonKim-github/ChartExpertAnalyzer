from __future__ import annotations

import hashlib
import re

from ..clustering import FeatureExtractor
from .models import EventRunResult, MaterialEvent
from .rules import infer_event_type, infer_polarity, infer_stage


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")
OFFICIAL_SOURCES = {"DART", "KIND", "MOTIR", "MSIT", "MCEE", "MFDS", "FSC"}


def _clean_summary(value: str | None, max_chars: int = 260) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    return text[:max_chars].rstrip()


def _first_sentence(value: str | None, max_chars: int = 260) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
    return (parts[0] if parts else text)[:max_chars].rstrip()


class EventExtractor:
    VERSION = "RULE_EVENT_V1"

    def __init__(self, event_repository, feature_extractor=None):
        self.repository = event_repository
        self.feature_extractor = feature_extractor or FeatureExtractor()

    def run(self, *, rebuild: bool = False, limit: int | None = None) -> EventRunResult:
        if rebuild:
            self.repository.clear_all()

        result = EventRunResult()
        self.repository.prune_orphans()
        clusters = self.repository.get_pending_clusters(limit=limit)

        for cluster in clusters:
            result.processed += 1
            members = self.repository.get_cluster_members(cluster["cluster_id"])
            event = self.extract(cluster, members)
            action = self.repository.upsert_event(event)
            if action == "INSERTED":
                result.inserted += 1
            else:
                result.updated += 1

        result.total_events = self.repository.event_count()
        return result

    def extract(self, cluster, members) -> MaterialEvent:
        representative = None
        for row in members:
            if row["article_id"] == cluster["representative_article_id"]:
                representative = row
                break
        representative = representative or (members[0] if members else None)
        if representative is None:
            raise ValueError(f"cluster has no members: {cluster['cluster_id']}")

        source_ids = {row["source_id"] for row in members}
        combined_parts = []
        companies = []
        stock_codes = []
        numbers = []

        for row in members:
            combined_parts.extend([
                row["title"] or "",
                row["summary"] or "",
                (row["body"] or "")[:1800],
            ])
            features = self.feature_extractor.extract(row)
            for company in features.companies:
                if company not in companies:
                    companies.append(company)
            for code in features.stock_codes:
                if code not in stock_codes:
                    stock_codes.append(code)
            for number in features.numbers:
                if number not in numbers:
                    numbers.append(number)

        combined = " ".join(part for part in combined_parts if part)
        event_type = infer_event_type(combined)
        event_stage = infer_stage(combined, source_ids)
        positive_negative = infer_polarity(combined, event_type)

        event_summary = (
            _clean_summary(representative["summary"])
            or _first_sentence(representative["body"])
            or _clean_summary(representative["title"])
        )

        confidence = 35.0
        if event_type != "UNKNOWN":
            confidence += 25
        if companies or stock_codes:
            confidence += 15
        if representative["source_id"] in OFFICIAL_SOURCES:
            confidence += 10
        if numbers:
            confidence += 5
        if int(cluster["source_count"] or 0) > 1:
            confidence += 5
        if int(cluster["confirmation_count"] or 0) > 0:
            confidence += 5
        confidence = round(min(100.0, confidence), 2)

        digest = hashlib.sha256(cluster["cluster_id"].encode("utf-8")).hexdigest()[:16]
        return MaterialEvent(
            event_id=f"EV_{digest}",
            cluster_id=cluster["cluster_id"],
            representative_article_id=cluster["representative_article_id"],
            event_type=event_type,
            event_stage=event_stage,
            event_title=representative["title"] or cluster["cluster_title"],
            event_summary=event_summary,
            positive_negative=positive_negative,
            quantified=bool(numbers),
            companies=tuple(companies),
            stock_codes=tuple(stock_codes),
            numbers=tuple(numbers),
            original_source_id=representative["source_id"] or "",
            original_source_name=representative["source_name"] or "",
            article_count=int(cluster["article_count"] or 0),
            source_count=int(cluster["source_count"] or 0),
            confirmation_count=int(cluster["confirmation_count"] or 0),
            first_seen_at=cluster["first_seen_at"],
            last_seen_at=cluster["last_seen_at"],
            market_date=cluster["market_date"],
            extraction_confidence=confidence,
            extraction_version=self.VERSION,
            cluster_updated_at=cluster["updated_at"],
        )
