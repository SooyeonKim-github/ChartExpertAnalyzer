from __future__ import annotations

from .models import MaterialScoreRecord, MaterialScoreRunResult, ScoreInput
from .rules import (
    direct_company_score,
    event_certainty_score,
    financial_impact_score,
    multi_source_score,
    novelty_component_score,
    quantification_score,
    source_reliability_score,
    status_from_score,
)


class MaterialScorer:
    VERSION = "RULE_MATERIAL_SCORE_V1"

    def __init__(self, repository):
        self.repository = repository

    @staticmethod
    def score_event(event: ScoreInput) -> MaterialScoreRecord:
        direct, direct_reason = direct_company_score(event)
        certainty, certainty_reason = event_certainty_score(event)
        impact, impact_reason = financial_impact_score(event)
        quant, quant_reason = quantification_score(event)
        novelty, novelty_reason = novelty_component_score(event)
        source, source_reason = source_reliability_score(event)
        multi, multi_reason = multi_source_score(event)

        total = round(direct + certainty + impact + quant + novelty + source + multi, 2)
        status = status_from_score(total)
        reasons = [
            f"direct={direct:g}({direct_reason})",
            f"certainty={certainty:g}({certainty_reason})",
            f"impact={impact:g}({impact_reason})",
            f"quant={quant:g}({quant_reason})",
            f"novelty={novelty:g}({novelty_reason})",
            f"source={source:g}({source_reason})",
            f"multi={multi:g}({multi_reason})",
        ]

        return MaterialScoreRecord(
            event_id=event.event_id,
            material_score=total,
            material_status=status,
            direct_company_score=direct,
            event_certainty_score=certainty,
            financial_impact_score=impact,
            quantification_score=quant,
            novelty_component_score=novelty,
            source_reliability_score=source,
            multi_source_score=multi,
            scoring_reason=" | ".join(reasons),
            scoring_version=MaterialScorer.VERSION,
            event_updated_at=event.event_updated_at,
            novelty_updated_at=event.novelty_updated_at,
        )

    def run(self, *, rebuild: bool = False, limit: int | None = None) -> MaterialScoreRunResult:
        if rebuild:
            self.repository.clear_all()

        self.repository.prune_ineligible()
        rows = self.repository.get_pending_events(
            scoring_version=self.VERSION,
            limit=limit,
        )
        result = MaterialScoreRunResult()

        for row in rows:
            result.processed += 1
            event = ScoreInput.from_row(row)
            record = self.score_event(event)
            action = self.repository.upsert_score(record)
            if action == "INSERTED":
                result.inserted += 1
            else:
                result.updated += 1

        result.total_scores = self.repository.score_count()
        counts = self.repository.status_counts()
        result.strong = counts.get("STRONG", 0)
        result.confirmed = counts.get("CONFIRMED", 0)
        result.watch = counts.get("WATCH", 0)
        result.reject = counts.get("REJECT", 0)
        return result
