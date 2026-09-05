from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher

from ..clustering.feature_extractor import normalize_title, tokenize
from .models import EventView, RelationResult


COMPATIBLE_EVENT_TYPES = {
    frozenset({"CLINICAL", "APPROVAL"}),
    frozenset({"INVESTMENT", "CAPEX"}),
}

GENERIC_EVENT_TOKENS = {
    "공급계약", "계약체결", "계약", "체결", "수주", "단일판매", "판매",
    "투자", "투자계획", "투자결정", "시설투자", "설비투자", "신규시설투자",
    "계획", "예정", "추진", "검토", "확정", "결정", "승인", "허가", "신청",
    "임상시험", "시험계획", "발표", "공시", "관련", "대한", "정부", "정책",
}


def _jaccard(left, right) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _informative_tokens(event: EventView, tokens) -> tuple[str, ...]:
    company_tokens = {
        normalize_title(company).replace(" ", "")
        for company in event.companies
        if company
    }
    result = []
    for token in tokens:
        compact = token.replace(" ", "")
        if compact in GENERIC_EVENT_TOKENS or compact in company_tokens:
            continue
        if token in event.stock_codes:
            continue
        result.append(token)
    return tuple(result)


def _date_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            a = datetime.strptime(left[:10].replace("-", "") if fmt == "%Y%m%d" else left[:10], fmt).date()
            b = datetime.strptime(right[:10].replace("-", "") if fmt == "%Y%m%d" else right[:10], fmt).date()
            return abs((a - b).days)
        except (ValueError, TypeError):
            continue
    return None


def _event_type_relation(left: str, right: str) -> tuple[float, str]:
    if left == right:
        return 25.0, "same_event_type"
    if frozenset({left, right}) in COMPATIBLE_EVENT_TYPES:
        return 18.0, "compatible_event_type"
    return -25.0, "event_type_conflict"


class RelationScorer:
    """Deterministic same-event-family scorer. No embeddings or semantic model."""

    MATCH_THRESHOLD = 68.0

    def score(self, current: EventView, candidate: EventView) -> RelationResult:
        current_title = normalize_title(current.event_title)
        candidate_title = normalize_title(candidate.event_title)
        current_tokens = tokenize(current_title)
        candidate_tokens = tokenize(candidate_title)
        current_info = _informative_tokens(current, current_tokens)
        candidate_info = _informative_tokens(candidate, candidate_tokens)

        title_ratio = (
            SequenceMatcher(None, current_title, candidate_title).ratio()
            if current_title and candidate_title
            else 0.0
        )
        token_overlap = _jaccard(current_tokens, candidate_tokens)
        informative_overlap = _jaccard(current_info, candidate_info)
        days_apart = _date_distance(current.market_date or current.first_seen_at, candidate.market_date or candidate.first_seen_at)

        current_stocks, candidate_stocks = set(current.stock_codes), set(candidate.stock_codes)
        current_companies, candidate_companies = set(current.companies), set(candidate.companies)
        stock_overlap = bool(current_stocks & candidate_stocks)
        company_overlap = bool(current_companies & candidate_companies)
        identity_present = bool(current_stocks or current.companies or candidate_stocks or candidate.companies)

        score = 0.0
        reasons: list[str] = []

        if stock_overlap:
            score += 35
            reasons.append("stock")
        elif company_overlap:
            score += 30
            reasons.append("company")
        elif identity_present:
            score -= 35
            reasons.append("identity_conflict")

        event_score, event_reason = _event_type_relation(current.event_type, candidate.event_type)
        score += event_score
        reasons.append(event_reason)

        score += 15 * token_overlap
        score += 10 * informative_overlap
        score += 10 * title_ratio

        current_numbers, candidate_numbers = set(current.numbers), set(candidate.numbers)
        number_overlap = bool(current_numbers & candidate_numbers)
        if current_numbers and candidate_numbers:
            if number_overlap:
                score += 8
                reasons.append("number_overlap")
            else:
                score -= 2
                reasons.append("number_delta")

        if days_apart is not None:
            if days_apart <= 7:
                score += 10
                reasons.append("recent_7d")
            elif days_apart <= 30:
                score += 7
            elif days_apart <= 90:
                score += 4
            elif days_apart <= 180:
                score += 1
            else:
                score -= 15

        # Different named companies/tickers must never become one family from title similarity alone.
        if identity_present and not stock_overlap and not company_overlap:
            score = min(score, 49.0)

        # Same company + event type is insufficient. Require a shared event-specific anchor,
        # a shared meaningful number, or a very strong stage-linked title continuation.
        if stock_overlap or company_overlap:
            no_anchor = not (set(current_info) & set(candidate_info))
            stage_link = current.event_stage != candidate.event_stage and title_ratio >= 0.65
            if no_anchor and not number_overlap and not stage_link:
                score = min(score, 62.0)
                reasons.append("event_anchor_guard")
            elif title_ratio < 0.35 and token_overlap < 0.25:
                score = min(score, 62.0)
                reasons.append("weak_title_guard")

        # Government/policy events may have no company. Require substantial lexical evidence.
        if not identity_present and current.event_type == candidate.event_type:
            if title_ratio < 0.50 and informative_overlap < 0.35:
                score = min(score, 62.0)
                reasons.append("no_identity_guard")

        return RelationResult(
            score=max(0.0, min(100.0, round(score, 2))),
            title_ratio=round(title_ratio, 4),
            token_overlap=round(token_overlap, 4),
            days_apart=days_apart,
            reason=",".join(reasons),
        )
