from __future__ import annotations

SOURCE_PRIORITY = {"DART": 1000, "KIND": 950}
TYPE_PRIORITY = {"OFFICIAL": 920, "GOV": 900, "NEWS": 800, "INDUSTRY": 700}
GRADE_BONUS = {"S": 40, "A": 20, "B": 10}


def representative_rank(row) -> tuple:
    return (
        SOURCE_PRIORITY.get(
            row["source_id"],
            TYPE_PRIORITY.get(row["source_type"] or "", 600),
        )
        + GRADE_BONUS.get(row["source_grade"] or "", 0),
        -(len(row["title"] or "")),
        row["first_seen_at"] or row["collected_at"] or "",
    )


class RepresentativeSelector:
    def choose(self, rows):
        if not rows:
            return None
        return max(rows, key=representative_rank)
