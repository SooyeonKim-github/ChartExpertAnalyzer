from __future__ import annotations

from .events.event_identity import build_canonical_event_key, build_document_signature


def _row(**kwargs):
    base = {
        "source_id": "DART",
        "external_id": "",
        "article_id": "",
        "canonical_url": "",
        "url": "",
        "published_at": "2026-09-16T09:00:00+00:00",
        "title": "",
    }
    base.update(kwargs)
    return base


def main():
    # Same source document -> same document signature even if display title changes.
    original_doc = build_document_signature(_row(
        external_id="20260916001234",
        article_id="DART_20260916001234",
        title="단일판매ㆍ공급계약체결",
    ))
    same_doc = build_document_signature(_row(
        external_id="20260916001234",
        article_id="DART_20260916001234",
        title="[기재정정]단일판매ㆍ공급계약체결",
    ))
    different_doc = build_document_signature(_row(
        external_id="20260916005678",
        article_id="DART_20260916005678",
        title="단일판매ㆍ공급계약체결",
    ))
    assert original_doc == same_doc
    assert original_doc != different_doc

    # A revision prefix must not change the event identity when the title itself carries
    # an event-specific discriminator such as the convertible-bond tranche number.
    original_event = build_canonical_event_key(
        event_type="CAPITAL_RAISE",
        event_title="자기전환사채매도결정 (4회차)",
        event_summary="자기전환사채매도결정 (4회차)",
        companies=("시선AI",),
        stock_codes=("340810",),
        market_date="20260910",
        source_id="DART",
    )
    revised_event = build_canonical_event_key(
        event_type="CAPITAL_RAISE",
        event_title="[기재정정]자기전환사채매도결정 (4회차)",
        event_summary="[기재정정]자기전환사채매도결정 (4회차)",
        companies=("시선AI",),
        stock_codes=("340810",),
        market_date="20260916",
        source_id="DART",
    )
    other_tranche = build_canonical_event_key(
        event_type="CAPITAL_RAISE",
        event_title="자기전환사채매도결정 (5회차)",
        event_summary="자기전환사채매도결정 (5회차)",
        companies=("시선AI",),
        stock_codes=("340810",),
        market_date="20260916",
        source_id="DART",
    )
    assert original_event == revised_event
    assert original_event != other_tranche

    # Generic disclosure titles are intentionally daily-scoped in V1.  Without parsed
    # counterparty/subject details, cross-date merging would collapse unrelated contracts.
    same_day_original = build_canonical_event_key(
        event_type="ORDER_CONTRACT",
        event_title="단일판매ㆍ공급계약체결",
        event_summary="단일판매ㆍ공급계약체결",
        companies=("테스트건설",),
        stock_codes=("123456",),
        market_date="20260916",
        source_id="DART",
    )
    same_day_revision = build_canonical_event_key(
        event_type="ORDER_CONTRACT",
        event_title="[기재정정]단일판매ㆍ공급계약체결",
        event_summary="[기재정정]단일판매ㆍ공급계약체결",
        companies=("테스트건설",),
        stock_codes=("123456",),
        market_date="20260916",
        source_id="DART",
    )
    next_day_contract = build_canonical_event_key(
        event_type="ORDER_CONTRACT",
        event_title="단일판매ㆍ공급계약체결",
        event_summary="단일판매ㆍ공급계약체결",
        companies=("테스트건설",),
        stock_codes=("123456",),
        market_date="20260917",
        source_id="DART",
    )
    assert same_day_original == same_day_revision
    assert same_day_original != next_day_contract

    print("[OK] EventIdentity V1 smoke test")
    print("     source document identity -> stable")
    print("     revision prefix -> canonicalized")
    print("     tranche discriminator -> preserved")
    print("     generic disclosure -> conservative daily scope")


if __name__ == "__main__":
    main()
