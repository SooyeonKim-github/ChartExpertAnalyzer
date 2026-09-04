from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher

from .disclosure_rules import DISCLOSURE_SOURCES, disclosure_bridge_id
from .models import ArticleFeatures, MatchResult


def _set_overlap(left, right) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _date_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    try:
        a = datetime.strptime(left, "%Y%m%d").date()
        b = datetime.strptime(right, "%Y%m%d").date()
    except ValueError:
        return None
    return abs((a - b).days)


class PairScorer:
    AUTO_MATCH_THRESHOLD = 80.0
    MIN_TITLE_RATIO = 0.45

    def score(self, article: ArticleFeatures, representative: ArticleFeatures) -> MatchResult:
        source_pair = {article.source_id, representative.source_id}
        title_ratio = (
            SequenceMatcher(None, article.normalized_title, representative.normalized_title).ratio()
            if article.normalized_title and representative.normalized_title
            else 0.0
        )
        token_overlap = _set_overlap(article.tokens, representative.tokens)
        company_overlap = bool(set(article.companies) & set(representative.companies))
        stock_overlap = bool(set(article.stock_codes) & set(representative.stock_codes))
        number_left, number_right = set(article.numbers), set(representative.numbers)
        numbers_overlap = bool(number_left & number_right)
        numbers_conflict = bool(number_left and number_right and not numbers_overlap)
        date_distance = _date_distance(article.market_date, representative.market_date)

        if (
            source_pair == DISCLOSURE_SOURCES
            and article.external_id
            and representative.external_id
            and article.external_id == representative.external_id
        ):
            return MatchResult(100.0, "DISCLOSURE_ID", "same DART/KIND receipt number")

        article_bridge = disclosure_bridge_id(article.external_id)
        representative_bridge = disclosure_bridge_id(representative.external_id)
        if (
            source_pair == DISCLOSURE_SOURCES
            and article_bridge
            and article_bridge == representative_bridge
            and (company_overlap or stock_overlap)
            and title_ratio >= 0.55
            and not numbers_conflict
        ):
            return MatchResult(
                98.0,
                "DART_KIND_BRIDGE_ID",
                f"same official bridge id {article_bridge}",
            )

        if source_pair == DISCLOSURE_SOURCES:
            if company_overlap and article.event_type == representative.event_type:
                if (
                    article.event_type != "UNKNOWN"
                    and title_ratio >= 0.72
                    and date_distance is not None
                    and date_distance <= 1
                    and not numbers_conflict
                ):
                    return MatchResult(
                        92.0,
                        "DART_KIND_RULE",
                        "same company/event with high title similarity",
                    )

        score = 0.0
        reasons = []

        if company_overlap:
            score += 30
            reasons.append("company")
        if stock_overlap:
            score += 10
            reasons.append("stock")

        if article.event_type != "UNKNOWN" and representative.event_type != "UNKNOWN":
            if article.event_type == representative.event_type:
                score += 25
                reasons.append("event")
            else:
                score -= 30
                reasons.append("event_conflict")

        score += 20 * title_ratio
        score += 10 * token_overlap

        if number_left and number_right:
            if numbers_overlap:
                score += 10
                reasons.append("number")
            else:
                score -= 20
                reasons.append("number_conflict")

        if date_distance == 0:
            score += 5
            reasons.append("same_day")
        elif date_distance == 1:
            score += 3
        elif date_distance == 2:
            score += 1
        elif date_distance is not None and date_distance > 2:
            score -= 15

        if (
            article.source_id in DISCLOSURE_SOURCES
            and representative.source_id in DISCLOSURE_SOURCES
            and company_overlap
            and title_ratio >= 0.90
            and date_distance is not None
            and date_distance <= 1
            and not numbers_conflict
        ):
            score = max(score, 88.0)
            reasons.append("official_title")

        if (
            article.event_type != "UNKNOWN"
            and article.event_type == representative.event_type
            and title_ratio >= 0.82
            and token_overlap >= 0.45
            and date_distance is not None
            and date_distance <= 1
            and not numbers_conflict
        ):
            score = max(score, 84.0)
            reasons.append("high_title_rule")

        if not company_overlap and not stock_overlap and title_ratio < self.MIN_TITLE_RATIO:
            score = min(score, 64.0)

        if (
            article.source_id == representative.source_id
            and article.source_id in DISCLOSURE_SOURCES
            and article.external_id
            and representative.external_id
            and article.external_id != representative.external_id
        ):
            score = min(score, 79.0)
            reasons.append("same_source_receipt_conflict")

        return MatchResult(
            max(0.0, min(100.0, round(score, 2))),
            "RULE_SCORE",
            ",".join(reasons) or "weak",
        )
