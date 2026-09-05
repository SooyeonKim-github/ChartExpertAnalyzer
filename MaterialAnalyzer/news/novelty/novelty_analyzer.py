from __future__ import annotations

import re

from .candidate_finder import CandidateFinder
from .delta_detector import DeltaDetector
from .family_builder import choose_family_id
from .models import DeltaResult, EventView, NoveltyRecord, NoveltyRunResult
from .novelty_classifier import NoveltyClassifier
from .relation_scorer import RelationScorer


MARKET_REACTION_RE = re.compile(
    r"(?:주가|증시|관련주|테마주).*(?:급등|강세|상한가|급락|약세|상승|하락)|"
    r"(?:급등|강세|상한가|급락|약세).*(?:주가|관련주|테마주)|"
    r"(?:소식에|기대감에|영향으로).*(?:급등|강세|상승|급락|약세|하락)",
    re.I,
)


class NoveltyAnalyzer:
    VERSION = "RULE_NOVELTY_V1"

    def __init__(
        self,
        repository,
        *,
        relation_scorer: RelationScorer | None = None,
        delta_detector: DeltaDetector | None = None,
        classifier: NoveltyClassifier | None = None,
    ):
        self.repository = repository
        self.relation_scorer = relation_scorer or RelationScorer()
        self.candidate_finder = CandidateFinder(
            repository,
            self.relation_scorer,
            analysis_version=self.VERSION,
        )
        self.delta_detector = delta_detector or DeltaDetector()
        self.classifier = classifier or NoveltyClassifier()

    @staticmethod
    def _is_market_reaction(event: EventView) -> bool:
        if (event.article_class or "").upper() == "MARKET_REACTION":
            return True
        return bool(MARKET_REACTION_RE.search(event.event_title or ""))

    def run(self, *, rebuild: bool = False, limit: int | None = None) -> NoveltyRunResult:
        if rebuild:
            self.repository.clear_all()

        self.repository.prune_ineligible()
        rows = self.repository.get_pending_events(
            analysis_version=self.VERSION,
            limit=limit,
        )
        result = NoveltyRunResult()

        for row in rows:
            event = EventView.from_row(row)
            result.processed += 1

            parent, parent_family_id, relation = self.candidate_finder.find_best_parent(event)
            is_market_reaction = self._is_market_reaction(event)

            delta: DeltaResult | None = None
            if parent is not None:
                delta = self.delta_detector.detect(event, parent)

            decision = self.classifier.classify(
                has_parent=parent is not None,
                is_market_reaction=is_market_reaction,
                delta=delta,
                relation=relation,
            )

            family_id = choose_family_id(event, parent_family_id)
            delta = delta or DeltaResult(
                previous_stage="",
                current_stage=event.event_stage,
                current_numbers=tuple(event.numbers),
            )

            record = NoveltyRecord(
                event_id=event.event_id,
                family_id=family_id,
                parent_event_id=parent.event_id if parent else None,
                novelty_status=decision.novelty_status,
                novelty_score=decision.novelty_score,
                relation_score=relation.score if relation else 0.0,
                days_since_parent=relation.days_apart if relation else None,
                stage_changed=delta.stage_changed,
                stage_progressed=delta.stage_progressed,
                number_changed=delta.number_changed,
                company_changed=delta.company_changed,
                polarity_changed=delta.polarity_changed,
                source_reliability_increased=delta.source_reliability_increased,
                confirmation_source_added=delta.confirmation_source_added,
                new_information_count=delta.new_information_count,
                previous_stage=delta.previous_stage,
                current_stage=delta.current_stage or event.event_stage,
                previous_numbers=delta.previous_numbers,
                current_numbers=delta.current_numbers or tuple(event.numbers),
                novelty_reason=decision.reason,
                analysis_version=self.VERSION,
                event_updated_at=event.updated_at,
            )

            action, previous_family_id = self.repository.upsert_novelty(record)
            self.repository.refresh_family(family_id, analysis_version=self.VERSION)
            if previous_family_id and previous_family_id != family_id:
                self.repository.refresh_family(previous_family_id, analysis_version=self.VERSION)

            if action == "INSERTED":
                result.inserted += 1
            else:
                result.updated += 1

        self.repository.prune_empty_families()
        result.total_novelty = self.repository.novelty_count()
        result.total_families = self.repository.family_count()
        counts = self.repository.status_counts()
        result.new_event = counts.get("NEW_EVENT", 0)
        result.follow_up = counts.get("FOLLOW_UP", 0)
        result.confirmation = counts.get("CONFIRMATION", 0)
        result.rehash = counts.get("REHASH", 0)
        result.market_reaction = counts.get("MARKET_REACTION", 0)
        return result
