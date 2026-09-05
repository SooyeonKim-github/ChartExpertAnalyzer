from __future__ import annotations

from datetime import datetime, timedelta

from .models import EventView, RelationResult
from .relation_scorer import RelationScorer


class CandidateFinder:
    def __init__(self, repository, relation_scorer: RelationScorer | None = None):
        self.repository = repository
        self.relation_scorer = relation_scorer or RelationScorer()

    @staticmethod
    def _window_start(event: EventView) -> str | None:
        if not event.market_date:
            return None
        try:
            base = datetime.strptime(event.market_date, "%Y%m%d").date()
        except ValueError:
            return None
        lookback = 180 if not (event.companies or event.stock_codes) else 120
        return (base - timedelta(days=lookback)).strftime("%Y%m%d")

    def find_best_parent(self, event: EventView):
        candidates = self.repository.get_prior_analyzed_events(
            event,
            start_market_date=self._window_start(event),
            limit=500,
        )
        best_event = None
        best_family_id = None
        best_relation: RelationResult | None = None

        for row in candidates:
            candidate = EventView.from_row(row)
            relation = self.relation_scorer.score(event, candidate)
            if relation.score < self.relation_scorer.MATCH_THRESHOLD:
                continue
            if (
                best_relation is None
                or relation.score > best_relation.score
                or (
                    relation.score == best_relation.score
                    and (candidate.first_seen_at or "") > (best_event.first_seen_at or "")
                )
            ):
                best_event = candidate
                best_family_id = row["family_id"]
                best_relation = relation

        return best_event, best_family_id, best_relation
