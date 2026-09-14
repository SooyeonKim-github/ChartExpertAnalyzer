from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KeywordMatch:
    keyword: str
    field: str
    weight: float
    strong: bool = False


@dataclass
class SectorMatch:
    sector: str
    sector_name_ko: str
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    subsectors: list[str] = field(default_factory=list)
    subsector_names_ko: list[str] = field(default_factory=list)


@dataclass
class ThemeMatch:
    theme_family: str
    theme_family_name_ko: str
    theme: str
    theme_name_ko: str
    description: str
    sectors: list[str]
    sector_names_ko: list[str]
    subsectors: list[str]
    subsector_names_ko: list[str]
    direction: str
    rule_score: float
    confidence: float
    matched_keywords: list[str]
    positive_hits: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    themes: list[ThemeMatch] = field(default_factory=list)
    sectors: list[SectorMatch] = field(default_factory=list)

    @property
    def has_theme(self) -> bool:
        return bool(self.themes)

    @property
    def has_sector(self) -> bool:
        return bool(self.sectors)


@dataclass
class AnalyzerStats:
    start_date: str
    end_date: str
    clusters_scanned: int = 0
    clusters_with_theme: int = 0
    theme_matches: int = 0
    sector_only_clusters: int = 0
