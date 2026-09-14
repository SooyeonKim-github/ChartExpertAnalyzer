from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


DETAIL_FIELDS = [
    "market_date",
    "classification_type",
    "cluster_id",
    "cluster_title",
    "representative_article_id",
    "representative_title",
    "theme",
    "theme_name_ko",
    "theme_description",
    "sectors",
    "sector_names_ko",
    "subsectors",
    "subsector_names_ko",
    "direction",
    "rule_score",
    "confidence",
    "matched_keywords",
    "positive_hits",
    "negative_hits",
    "article_count",
    "source_count",
    "confirmation_count",
    "cluster_confidence",
    "first_seen_at",
    "last_seen_at",
    "published_at",
    "source_id",
    "source_name",
    "source_grade",
    "article_class",
    "url",
    "analyzer_version",
    "classifier_version",
]

SUMMARY_FIELDS = [
    "market_date",
    "theme",
    "theme_name_ko",
    "sectors",
    "sector_names_ko",
    "subsectors",
    "subsector_names_ko",
    "direction",
    "cluster_count",
    "article_count",
    "source_evidence_count",
    "max_rule_score",
    "max_confidence",
    "matched_keywords",
    "representative_title",
]


class ThemeSectorReporter:
    @staticmethod
    def export_detail(rows: list[dict], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return output

    @staticmethod
    def export_daily_summary(rows: list[dict], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in rows:
            if row.get("classification_type") != "THEME" or not row.get("theme"):
                continue
            grouped[(str(row.get("market_date") or ""), str(row["theme"]))].append(row)

        summary_rows: list[dict] = []
        for (market_date, theme), items in grouped.items():
            ranked = sorted(
                items,
                key=lambda item: (
                    float(item.get("rule_score") or 0),
                    float(item.get("confidence") or 0),
                ),
                reverse=True,
            )
            lead = ranked[0]
            directions = {str(item.get("direction") or "NEUTRAL") for item in items}
            direction = next(iter(directions)) if len(directions) == 1 else "MIXED"
            keywords = _pipe_union(item.get("matched_keywords") for item in items)
            sectors = _pipe_union(item.get("sectors") for item in items)
            sector_names = _pipe_union(item.get("sector_names_ko") for item in items)
            subsectors = _pipe_union(item.get("subsectors") for item in items)
            subsector_names = _pipe_union(item.get("subsector_names_ko") for item in items)

            summary_rows.append(
                {
                    "market_date": market_date,
                    "theme": theme,
                    "theme_name_ko": lead.get("theme_name_ko", ""),
                    "sectors": sectors,
                    "sector_names_ko": sector_names,
                    "subsectors": subsectors,
                    "subsector_names_ko": subsector_names,
                    "direction": direction,
                    "cluster_count": len({item.get("cluster_id") for item in items}),
                    "article_count": sum(int(item.get("article_count") or 0) for item in items),
                    # This is evidence volume, not a unique global source count.  Each
                    # ArticleCluster already calculates its own distinct source_count.
                    "source_evidence_count": sum(
                        int(item.get("source_count") or 0) for item in items
                    ),
                    "max_rule_score": max(float(item.get("rule_score") or 0) for item in items),
                    "max_confidence": max(float(item.get("confidence") or 0) for item in items),
                    "matched_keywords": keywords,
                    "representative_title": lead.get("representative_title", ""),
                }
            )

        summary_rows.sort(
            key=lambda item: (
                item["market_date"],
                float(item["max_rule_score"]),
                int(item["cluster_count"]),
            ),
            reverse=True,
        )

        with output.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
            writer.writeheader()
            writer.writerows(summary_rows)
        return output


def _pipe_union(values) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        for item in str(value or "").split("|"):
            item = item.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
    return "|".join(result)
