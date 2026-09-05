from __future__ import annotations

from .models import DeltaResult, NoveltyDecision, RelationResult


class NoveltyClassifier:
    def classify(
        self,
        *,
        has_parent: bool,
        is_market_reaction: bool,
        delta: DeltaResult | None,
        relation: RelationResult | None,
    ) -> NoveltyDecision:
        if is_market_reaction:
            return NoveltyDecision(
                novelty_status="MARKET_REACTION",
                novelty_score=5.0,
                reason="market reaction article, not new catalyst information",
            )

        if not has_parent or delta is None:
            return NoveltyDecision(
                novelty_status="NEW_EVENT",
                novelty_score=100.0,
                reason="no sufficiently related prior material event",
            )

        follow_up_reasons: list[str] = []
        score = 60.0
        if delta.stage_changed:
            score += 10
            follow_up_reasons.append("stage_changed")
        if delta.stage_progressed:
            score += 5
            follow_up_reasons.append("stage_progressed")
        if delta.number_changed:
            score += 10
            follow_up_reasons.append("meaningful_number_changed")
        if delta.company_changed:
            score += 10
            follow_up_reasons.append("new_company_or_counterparty")
        if delta.polarity_changed:
            score += 15
            follow_up_reasons.append("polarity_changed")

        if follow_up_reasons:
            return NoveltyDecision(
                novelty_status="FOLLOW_UP",
                novelty_score=min(100.0, score),
                reason=",".join(follow_up_reasons),
            )

        if delta.source_reliability_increased or delta.confirmation_source_added:
            confirmation_score = 55.0
            reasons: list[str] = []
            if delta.source_reliability_increased:
                confirmation_score += 10
                reasons.append("source_reliability_increased")
            if delta.confirmation_source_added:
                confirmation_score += 5
                reasons.append("confirmation_source_added")
            return NoveltyDecision(
                novelty_status="CONFIRMATION",
                novelty_score=min(75.0, confirmation_score),
                reason=",".join(reasons),
            )

        relation_note = f"relation={relation.score:.1f}" if relation else "related"
        return NoveltyDecision(
            novelty_status="REHASH",
            novelty_score=15.0,
            reason=f"same event family without meaningful delta ({relation_note})",
        )
