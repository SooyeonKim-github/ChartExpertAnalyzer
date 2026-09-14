from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from .master_loader import MasterCatalog
from .models import ClassificationResult, SectorMatch, ThemeMatch


_FIELD_WEIGHTS = {
    "title": 2.0,
    "summary": 1.2,
    "body": 0.45,
}


class RuleClassifier:
    """Deterministic rule classifier driven entirely by theme_master.yaml.

    V1.2 removes theme-specific Python gates. Precision constraints are declared
    per theme with rules.scope / require_any / require_all / exclude_any, so new
    market themes can be added or tuned without changing classifier code.
    """

    VERSION = "THEME_SECTOR_RULE_V1_2"

    def __init__(self, catalog: MasterCatalog):
        self.catalog = catalog

    def classify(
        self,
        *,
        title: str | None,
        summary: str | None = None,
        body: str | None = None,
    ) -> ClassificationResult:
        fields = {
            "title": _normalize(title or ""),
            "summary": _normalize(summary or ""),
            "body": _normalize((body or "")[:12000]),
        }

        sector_matches = self._classify_sectors(fields)
        theme_matches = self._classify_themes(fields, sector_matches)
        return ClassificationResult(themes=theme_matches, sectors=sector_matches)

    def _classify_sectors(self, fields: dict[str, str]) -> list[SectorMatch]:
        matches: list[SectorMatch] = []
        for sector, cfg in self.catalog.sectors.items():
            keywords = _unique(
                [*list(cfg.get("aliases") or []), *list(cfg.get("keywords") or [])]
            )
            score, hits, _ = self._score_keywords(fields, keywords, strong=False)

            subsectors: list[str] = []
            subsector_names: list[str] = []
            for subsector, sub_cfg in (cfg.get("subsectors") or {}).items():
                sub_keywords = _unique(
                    [
                        *list(sub_cfg.get("aliases") or []),
                        *list(sub_cfg.get("keywords") or []),
                    ]
                )
                sub_score, _, _ = self._score_keywords(fields, sub_keywords, strong=False)
                if sub_score >= 1.5:
                    subsectors.append(subsector)
                    subsector_names.append(str(sub_cfg.get("name_ko") or subsector))

            if score < 1.5 and not subsectors:
                continue
            matches.append(
                SectorMatch(
                    sector=sector,
                    sector_name_ko=str(cfg.get("name_ko") or sector),
                    score=round(score, 2),
                    matched_keywords=hits,
                    subsectors=subsectors,
                    subsector_names_ko=subsector_names,
                )
            )

        matches.sort(key=lambda item: (-item.score, item.sector))
        return matches

    def _classify_themes(
        self,
        fields: dict[str, str],
        sector_matches: list[SectorMatch],
    ) -> list[ThemeMatch]:
        result: list[ThemeMatch] = []
        explicit_sector_codes = [m.sector for m in sector_matches]
        explicit_subsector_codes = {
            sub for match in sector_matches for sub in match.subsectors
        }

        for theme, cfg in self.catalog.themes.items():
            normal_keywords = list(cfg.get("keywords") or [])
            strong_keywords = list(cfg.get("strong_keywords") or [])
            legacy_excludes = list(cfg.get("exclude_keywords") or [])

            if any(self._contains_in_any(fields, keyword) for keyword in legacy_excludes):
                continue

            normal_score, normal_hits, _ = self._score_keywords(
                fields, normal_keywords, strong=False
            )
            strong_score, strong_hits, strong_hit_count = self._score_keywords(
                fields, strong_keywords, strong=True
            )
            score = normal_score + strong_score
            min_score = float(cfg.get("min_score", 2.0))
            if score < min_score:
                continue

            rules = cfg.get("rules") or {}
            if not self._passes_rules(fields, rules):
                continue

            configured_sectors = [str(x) for x in (cfg.get("sectors") or [])]
            configured_subsectors = [str(x) for x in (cfg.get("subsectors") or [])]

            sectors = configured_sectors or explicit_sector_codes
            sector_names = [self.catalog.sector_name(code) for code in sectors]

            if configured_subsectors:
                subsectors = configured_subsectors
            elif configured_sectors:
                subsectors = sorted(
                    sub
                    for sub in explicit_subsector_codes
                    if _subsector_parent(self.catalog, sub) in configured_sectors
                )
            else:
                subsectors = sorted(explicit_subsector_codes)
            subsector_names = [self.catalog.subsector_name(code) for code in subsectors]

            fixed_direction = str(cfg.get("fixed_direction") or "").upper()
            if fixed_direction:
                direction = fixed_direction
                positive_hits: list[str] = []
                negative_hits: list[str] = []
            else:
                direction, positive_hits, negative_hits = self._direction(fields, cfg)

            confidence = self._confidence(
                score=score,
                min_score=min_score,
                strong_hit_count=strong_hit_count,
            )
            family = str(cfg.get("family") or "")

            result.append(
                ThemeMatch(
                    theme_family=family,
                    theme_family_name_ko=self.catalog.family_name(family),
                    theme=theme,
                    theme_name_ko=str(cfg.get("name_ko") or theme),
                    description=str(cfg.get("description") or ""),
                    sectors=_unique(sectors),
                    sector_names_ko=_unique(sector_names),
                    subsectors=_unique(subsectors),
                    subsector_names_ko=_unique(subsector_names),
                    direction=direction,
                    rule_score=round(score, 2),
                    confidence=confidence,
                    matched_keywords=_unique([*strong_hits, *normal_hits]),
                    positive_hits=positive_hits,
                    negative_hits=negative_hits,
                )
            )

        result.sort(key=lambda item: (-item.rule_score, -item.confidence, item.theme))
        return result

    def _passes_rules(self, fields: dict[str, str], rules: dict) -> bool:
        if not rules:
            return True

        scoped_fields = _scope_fields(fields, str(rules.get("scope") or "all"))
        require_any = list(rules.get("require_any") or [])
        require_all = list(rules.get("require_all") or [])
        exclude_any = list(rules.get("exclude_any") or [])

        if require_any and not any(
            self._contains_in_any(scoped_fields, keyword) for keyword in require_any
        ):
            return False

        if require_all and not all(
            self._contains_in_any(scoped_fields, keyword) for keyword in require_all
        ):
            return False

        if exclude_any and any(
            self._contains_in_any(scoped_fields, keyword) for keyword in exclude_any
        ):
            return False

        return True

    def _direction(
        self,
        fields: dict[str, str],
        theme_cfg: dict,
    ) -> tuple[str, list[str], list[str]]:
        positive_keywords = _unique(
            [
                *self.catalog.positive_direction_keywords,
                *list(theme_cfg.get("positive_keywords") or []),
            ]
        )
        negative_keywords = _unique(
            [
                *self.catalog.negative_direction_keywords,
                *list(theme_cfg.get("negative_keywords") or []),
            ]
        )
        positive_hits = [
            keyword for keyword in positive_keywords if self._contains_in_any(fields, keyword)
        ]
        negative_hits = [
            keyword for keyword in negative_keywords if self._contains_in_any(fields, keyword)
        ]

        if positive_hits and negative_hits:
            if len(positive_hits) > len(negative_hits):
                direction = "POSITIVE"
            elif len(negative_hits) > len(positive_hits):
                direction = "NEGATIVE"
            else:
                direction = "MIXED"
        elif positive_hits:
            direction = "POSITIVE"
        elif negative_hits:
            direction = "NEGATIVE"
        else:
            direction = str(theme_cfg.get("default_direction") or "NEUTRAL").upper()

        return direction, positive_hits, negative_hits

    def _score_keywords(
        self,
        fields: dict[str, str],
        keywords: Iterable[str],
        *,
        strong: bool,
    ) -> tuple[float, list[str], int]:
        base = 2.0 if strong else 1.0
        total = 0.0
        hits: list[str] = []
        hit_count = 0
        for raw_keyword in _unique([str(k) for k in keywords if str(k).strip()]):
            keyword = _normalize(raw_keyword)
            best_weight = 0.0
            for field, text in fields.items():
                if _contains(text, keyword):
                    best_weight = max(best_weight, _FIELD_WEIGHTS[field])
            if best_weight <= 0:
                continue
            total += base * best_weight
            hits.append(raw_keyword)
            hit_count += 1
        return total, hits, hit_count

    @staticmethod
    def _contains_in_any(fields: dict[str, str], raw_keyword: str) -> bool:
        keyword = _normalize(str(raw_keyword))
        return any(_contains(text, keyword) for text in fields.values())

    @staticmethod
    def _confidence(*, score: float, min_score: float, strong_hit_count: int) -> float:
        margin = max(0.0, score - min_score)
        confidence = 64.0 + min(21.0, margin * 5.0) + min(12.0, strong_hit_count * 4.0)
        return round(min(99.0, confidence), 2)


def _scope_fields(fields: dict[str, str], scope: str) -> dict[str, str]:
    normalized = scope.lower()
    if normalized == "title":
        return {"title": fields.get("title", "")}
    if normalized == "summary":
        return {"summary": fields.get("summary", "")}
    if normalized == "title_summary":
        return {
            "title": fields.get("title", ""),
            "summary": fields.get("summary", ""),
        }
    return fields


def _subsector_parent(catalog: MasterCatalog, subsector: str) -> str | None:
    for sector, cfg in catalog.sectors.items():
        if subsector in (cfg.get("subsectors") or {}):
            return sector
    return None


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _contains(text: str, keyword: str) -> bool:
    if not keyword:
        return False
    if re.fullmatch(r"[a-z0-9.+-]+", keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = str(value)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
