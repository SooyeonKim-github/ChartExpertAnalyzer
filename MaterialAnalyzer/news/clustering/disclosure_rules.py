from __future__ import annotations

from collections import Counter, defaultdict

DISCLOSURE_SOURCES = {"DART", "KIND"}


def disclosure_bridge_id(external_id: str | None) -> str | None:
    """Bridge DART/KIND receipt ids that differ only by the market-system digit.

    Observed official ids use YYYYMMDD + one system digit + a five-digit sequence,
    e.g. DART 20260904900749 and KIND 20260904000749.
    """
    if not external_id:
        return None
    digits = "".join(ch for ch in str(external_id) if ch.isdigit())
    if len(digits) != 14:
        return None
    return f"{digits[:8]}:{digits[-5:]}"


class DisclosureAmbiguityGuard:
    """Block generic DART/KIND joins when the same company/title repeats that day."""

    def __init__(self, feature_extractor):
        self.feature_extractor = feature_extractor
        self._groups: dict[tuple[str, str, str], Counter] = defaultdict(Counter)

    def prepare(self, rows) -> None:
        self._groups.clear()
        for row in rows:
            features = self.feature_extractor.extract(row)
            if features.source_id not in DISCLOSURE_SOURCES:
                continue
            if not features.market_date or not features.normalized_title or not features.companies:
                continue
            for company in features.companies:
                key = (features.market_date, company, features.normalized_title)
                self._groups[key][features.source_id] += 1

    def is_ambiguous_pair(self, left, right, *, match_method: str = "") -> bool:
        if {left.source_id, right.source_id} != DISCLOSURE_SOURCES:
            return False
        if match_method in {"DISCLOSURE_ID", "DART_KIND_BRIDGE_ID"}:
            return False
        if not left.market_date or left.market_date != right.market_date:
            return False
        if not left.normalized_title or left.normalized_title != right.normalized_title:
            return False

        shared_companies = set(left.companies) & set(right.companies)
        if not shared_companies:
            return False

        for company in shared_companies:
            counts = self._groups.get(
                (left.market_date, company, left.normalized_title),
                Counter(),
            )
            if counts.get("DART", 0) > 1 or counts.get("KIND", 0) > 1:
                return True
        return False
