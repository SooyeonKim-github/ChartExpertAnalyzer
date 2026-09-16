from __future__ import annotations

from .disclosure_delta.detector import DisclosureDeltaDetector, comparable_pair, is_revision_title, revision_base_title
from .disclosure_delta.models import DisclosureDeltaInput
from .novelty.models import DeltaResult
from .novelty.novelty_classifier import NoveltyClassifier
from .scoring.material_scorer import MaterialScorer
from .scoring.models import ScoreInput


def _event(
    event_id: str,
    title: str,
    numbers: tuple[str, ...],
    *,
    event_type: str = "ORDER_CONTRACT",
    sentiment: str = "POSITIVE",
) -> DisclosureDeltaInput:
    return DisclosureDeltaInput(
        event_id=event_id,
        canonical_event_key="CEK_TEST_CONTRACT",
        event_type=event_type,
        event_stage="CONFIRMED",
        event_title=title,
        event_summary=title,
        positive_negative=sentiment,
        companies=("테스트기업",),
        stock_codes=("123456",),
        numbers=numbers,
        original_source_id="DART",
        first_seen_at="2026-09-16T09:00:00+09:00",
        market_date="20260916",
        event_updated_at="2026-09-16 10:00:00",
    )


def main():
    detector = DisclosureDeltaDetector()
    classifier = NoveltyClassifier()

    assert is_revision_title("[기재정정] 단일판매ㆍ공급계약체결")
    assert not is_revision_title("단일판매ㆍ공급계약체결")
    assert revision_base_title("[기재정정] 단일판매ㆍ공급계약체결") == revision_base_title(
        "단일판매ㆍ공급계약체결"
    )

    pair = comparable_pair(("500억원",), ("300억원",))
    assert pair is not None
    assert pair[0].kind == "money"
    assert pair[0].value == 50_000_000_000
    assert pair[1].value == 30_000_000_000

    parent = _event("EV_PARENT", "단일판매ㆍ공급계약체결", ("500억원",))
    correction = _event("EV_CORRECTION", "[기재정정] 단일판매ㆍ공급계약체결", ("300억원",))
    decrease = detector.detect(
        correction,
        parent,
        parent_match_method="CANONICAL_EVENT_KEY",
        parent_match_confidence=100.0,
    )
    assert decrease.is_revision
    assert decrease.parent_event_id == "EV_PARENT"
    assert decrease.delta_type == "CONTRACT_DECREASE"
    assert decrease.delta_direction == "DECREASE"
    assert decrease.effective_sentiment == "NEGATIVE"
    assert decrease.numeric_change_pct == -40.0
    # Material score measures importance, not bullishness. A verified large decrease
    # remains material while the direction is carried by effective_sentiment.
    assert decrease.score_adjustment == 5.0

    increase_correction = _event(
        "EV_INCREASE",
        "[기재정정] 단일판매ㆍ공급계약체결",
        ("600억원",),
    )
    increase = detector.detect(increase_correction, parent)
    assert increase.delta_type == "CONTRACT_INCREASE"
    assert increase.effective_sentiment == "POSITIVE"
    assert increase.score_adjustment == 5.0

    unresolved = detector.detect(correction, None, ambiguous_parent=True)
    assert unresolved.delta_type == "REVISION_UNRESOLVED"
    assert unresolved.effective_sentiment == "NEUTRAL"
    assert unresolved.score_adjustment == -25.0

    revision_decision = classifier.classify(
        has_parent=True,
        is_market_reaction=False,
        delta=DeltaResult(number_changed=True),
        relation=None,
        is_revision=True,
        disclosure_delta_type="CONTRACT_DECREASE",
    )
    assert revision_decision.novelty_status == "EXISTING_EVENT_REVISION"

    unresolved_decision = classifier.classify(
        has_parent=False,
        is_market_reaction=False,
        delta=None,
        relation=None,
        is_revision=True,
        disclosure_delta_type="REVISION_UNRESOLVED",
    )
    assert unresolved_decision.novelty_status == "REVISION_UNRESOLVED"

    score_input = ScoreInput(
        event_id="EV_CORRECTION",
        event_type="ORDER_CONTRACT",
        event_stage="CONFIRMED",
        event_title="[기재정정] 단일판매ㆍ공급계약체결",
        positive_negative="POSITIVE",
        companies=("테스트기업",),
        stock_codes=("123456",),
        numbers=("300억원",),
        original_source_id="DART",
        source_grade="S",
        source_type="OFFICIAL",
        novelty_status="EXISTING_EVENT_REVISION",
        novelty_score=75.0,
        disclosure_is_revision=True,
        disclosure_delta_type="CONTRACT_DECREASE",
        effective_sentiment="NEGATIVE",
        disclosure_score_adjustment=5.0,
    )
    scored = MaterialScorer.score_event(score_input)
    assert "disclosure_delta=+5" in scored.scoring_reason
    assert scored.material_score >= 85.0

    unresolved_score_input = ScoreInput(
        event_id="EV_UNRESOLVED",
        event_type="ORDER_CONTRACT",
        event_stage="CONFIRMED",
        event_title="[기재정정] 단일판매ㆍ공급계약체결",
        positive_negative="POSITIVE",
        companies=("테스트기업",),
        stock_codes=("123456",),
        numbers=(),
        original_source_id="DART",
        source_grade="S",
        source_type="OFFICIAL",
        novelty_status="REVISION_UNRESOLVED",
        disclosure_is_revision=True,
        disclosure_delta_type="REVISION_UNRESOLVED",
        effective_sentiment="NEUTRAL",
        disclosure_score_adjustment=-25.0,
    )
    unresolved_score = MaterialScorer.score_event(unresolved_score_input)
    assert unresolved_score.material_score < 55.0

    print("[OK] DisclosureDeltaAnalyzer V1 smoke test")
    print("     revision prefix detection -> OK")
    print("     500억원 -> 300억원 = CONTRACT_DECREASE / NEGATIVE -> OK")
    print("     500억원 -> 600억원 = CONTRACT_INCREASE / POSITIVE -> OK")
    print("     materiality score is direction-neutral for verified large deltas -> OK")
    print("     ambiguous parent = REVISION_UNRESOLVED / NEUTRAL -> OK")
    print("     novelty revision != NEW_EVENT -> OK")
    print("     unresolved revision score is capped down -> OK")


if __name__ == "__main__":
    main()
