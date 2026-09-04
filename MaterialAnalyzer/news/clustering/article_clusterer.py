from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .disclosure_rules import DisclosureAmbiguityGuard
from .feature_extractor import FeatureExtractor
from .pair_scorer import PairScorer


@dataclass
class ClusterRunResult:
    processed: int = 0
    matched: int = 0
    created: int = 0
    skipped: int = 0
    ambiguity_blocked: int = 0
    multi_member_clusters: int = 0
    total_clusters: int = 0


def _nearby_market_dates(value: str | None, days: int = 2) -> list[str]:
    if not value:
        return []
    try:
        base = datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return [value]
    return [
        (base + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(-days, days + 1)
    ]


class ArticleClusterer:
    VERSION = "RULE_CLUSTER_V1_1"

    def __init__(self, cluster_repository, feature_extractor=None, pair_scorer=None):
        self.repository = cluster_repository
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.pair_scorer = pair_scorer or PairScorer()
        self.ambiguity_guard = DisclosureAmbiguityGuard(self.feature_extractor)

    def run(self, *, rebuild: bool = False, limit: int | None = None) -> ClusterRunResult:
        if rebuild:
            self.repository.clear_all()

        self.ambiguity_guard.prepare(self.repository.get_disclosure_articles())

        result = ClusterRunResult()
        articles = self.repository.get_unclustered_articles(limit=limit)

        for article in articles:
            result.processed += 1
            features = self.feature_extractor.extract(article)

            exact_cluster = None
            if features.source_id in {"DART", "KIND"} and features.external_id:
                found = self.repository.find_cluster_by_external_id(features.external_id)
                if found:
                    exact_cluster = found["cluster_id"]

            if exact_cluster:
                self.repository.add_member(
                    exact_cluster,
                    article["article_id"],
                    100.0,
                    "DISCLOSURE_ID",
                    "same DART/KIND receipt number",
                )
                self.repository.refresh_cluster(exact_cluster)
                result.matched += 1
                continue

            best = None
            best_features = None
            best_match = None
            market_dates = _nearby_market_dates(features.market_date)
            candidates = self.repository.candidate_representatives(market_dates)

            for candidate in candidates:
                if candidate["article_id"] == article["article_id"]:
                    continue
                representative_features = self.feature_extractor.extract(candidate)
                match = self.pair_scorer.score(features, representative_features)
                if best_match is None or match.score > best_match.score:
                    best = candidate
                    best_features = representative_features
                    best_match = match

            blocked = False
            if (
                best is not None
                and best_features is not None
                and best_match is not None
                and best_match.score >= self.pair_scorer.AUTO_MATCH_THRESHOLD
            ):
                blocked = self.ambiguity_guard.is_ambiguous_pair(
                    features,
                    best_features,
                    match_method=best_match.method,
                )

            if (
                best is not None
                and best_match is not None
                and best_match.score >= self.pair_scorer.AUTO_MATCH_THRESHOLD
                and not blocked
            ):
                self.repository.add_member(
                    best["cluster_id"],
                    article["article_id"],
                    best_match.score,
                    best_match.method,
                    best_match.reason,
                )
                self.repository.refresh_cluster(best["cluster_id"])
                result.matched += 1
            else:
                if blocked:
                    result.ambiguity_blocked += 1
                cluster_id = self.repository.create_cluster(article, features)
                self.repository.refresh_cluster(cluster_id)
                result.created += 1

        result.total_clusters = self.repository.cluster_count()
        result.multi_member_clusters = self.repository.multi_member_count()
        return result
