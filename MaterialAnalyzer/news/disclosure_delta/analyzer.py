from __future__ import annotations

from datetime import datetime, timedelta

from .detector import (
    DisclosureDeltaDetector,
    generic_revision_anchor,
    input_from_row,
    is_revision_title,
    revision_base_title,
)
from .models import DisclosureDeltaRunResult


class DisclosureDeltaAnalyzer:
    VERSION = DisclosureDeltaDetector.VERSION

    def __init__(self, repository, detector: DisclosureDeltaDetector | None = None):
        self.repository = repository
        self.detector = detector or DisclosureDeltaDetector()

    @staticmethod
    def _fallback_window_start(market_date: str | None) -> str | None:
        if not market_date:
            return None
        try:
            base = datetime.strptime(market_date, "%Y%m%d").date()
        except ValueError:
            return None
        return (base - timedelta(days=180)).strftime("%Y%m%d")

    def _find_parent(self, event):
        if not is_revision_title(event.event_title):
            return None, "", 0.0, False

        exact = self.repository.find_exact_canonical_parent(event)
        if exact is not None:
            return input_from_row(exact), "CANONICAL_EVENT_KEY", 100.0, False

        candidates = self.repository.find_revision_candidates(
            event,
            start_market_date=self._fallback_window_start(event.market_date),
            limit=50,
        )
        base_title = revision_base_title(event.event_title)
        matched = [row for row in candidates if revision_base_title(row["event_title"]) == base_title]
        if not matched:
            return None, "TITLE_COMPANY_FALLBACK", 0.0, False

        if len(matched) == 1:
            confidence = 70.0 if generic_revision_anchor(event.event_title) else 90.0
            return input_from_row(matched[0]), "TITLE_COMPANY_FALLBACK", confidence, False

        # Generic disclosure titles (e.g. 단일판매ㆍ공급계약체결) can occur repeatedly for
        # one company. Without contract detail, choosing the newest row would silently link
        # the correction to the wrong contract, so keep it unresolved.
        if generic_revision_anchor(event.event_title):
            return None, "AMBIGUOUS_GENERIC_TITLE", 0.0, True

        # A discriminative suffix such as '(4회차)' remains in base_title. If multiple
        # rows still match, the most recent prior row is a reasonable revision parent.
        return input_from_row(matched[0]), "DISCRIMINATIVE_TITLE", 85.0, False

    def run(self, *, rebuild: bool = False, limit: int | None = None) -> DisclosureDeltaRunResult:
        if rebuild:
            self.repository.clear_all()

        self.repository.prune_orphans()
        rows = self.repository.get_pending_events(analysis_version=self.VERSION, limit=limit)
        result = DisclosureDeltaRunResult()

        for row in rows:
            event = input_from_row(row)
            parent, method, confidence, ambiguous = self._find_parent(event)
            record = self.detector.detect(
                event,
                parent,
                parent_match_method=method,
                parent_match_confidence=confidence,
                ambiguous_parent=ambiguous,
            )
            action = self.repository.upsert(record)
            result.processed += 1
            if action == "INSERTED":
                result.inserted += 1
            else:
                result.updated += 1

        result.total = self.repository.count()
        counts = self.repository.delta_type_counts()
        result.originals = counts.get("ORIGINAL", 0)
        result.revisions = sum(count for key, count in counts.items() if key != "ORIGINAL")
        result.unresolved = counts.get("REVISION_UNRESOLVED", 0)
        result.increases = sum(count for key, count in counts.items() if key.endswith("_INCREASE"))
        result.decreases = sum(count for key, count in counts.items() if key.endswith("_DECREASE"))
        result.minor = counts.get("MINOR_REVISION", 0)
        return result
