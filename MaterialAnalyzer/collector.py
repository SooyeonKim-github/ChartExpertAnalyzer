from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .collectors import NaverNewsCollector, OpenDartCollector, PolicyBriefingCollector, ScheduleCollector
from .config import DEFAULT_CONFIG, MaterialCollectorConfig
from .models import CollectedItem
from .schedule_models import ScheduleItem


@dataclass
class CollectionReport:
    items: list[CollectedItem]
    source_counts: dict[str, int]
    warnings: list[str]
    schedules: list[ScheduleItem] = field(default_factory=list)
    snapshot_file: Path | None = None
    history_file: Path | None = None
    schedule_snapshot_file: Path | None = None
    schedule_history_file: Path | None = None


class MaterialCollector:
    """Collect raw catalyst candidates without assigning investment scores.

    Raw collection and future-event extraction stay separate. ScheduleCollector turns
    already collected news/policy/disclosure text into explicit dated event rows, so
    later material scoring can use a clean future-event calendar without changing the
    raw material schema.
    """

    def __init__(self, config: MaterialCollectorConfig = DEFAULT_CONFIG, base_dir: Path | None = None) -> None:
        self.config = config
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.naver = NaverNewsCollector(config)
        self.dart = OpenDartCollector(config)
        self.policy = PolicyBriefingCollector(config)
        self.schedule = ScheduleCollector(config)

    def load_queries(self, path: Path | None = None, limit: int | None = None) -> list[tuple[str, str]]:
        path = path or self.base_dir / self.config.query_file
        queries: list[tuple[str, str]] = []
        if not path.exists():
            return queries

        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                enabled = str(row.get("enabled", "1")).strip().lower()
                if enabled in {"0", "false", "n", "no"}:
                    continue
                query = str(row.get("query", "")).strip()
                if not query:
                    continue
                category = str(row.get("category", "general")).strip() or "general"
                queries.append((category, query))
                if limit is not None and len(queries) >= limit:
                    break
        return queries

    def collect(
        self,
        target_date: date,
        days: int = 2,
        sources: Iterable[str] = ("naver", "policy", "dart", "schedule"),
        query_limit: int | None = None,
        schedule_lookahead_days: int | None = None,
    ) -> CollectionReport:
        selected = {s.strip().lower() for s in sources if s.strip()}
        unknown = selected - {"naver", "policy", "dart", "schedule"}
        collected_at = datetime.now().astimezone().isoformat()
        raw_items: list[CollectedItem] = []
        warnings: list[str] = []
        source_counts: dict[str, int] = {}

        if unknown:
            warnings.append(f"Unknown sources ignored: {', '.join(sorted(unknown))}")

        if "naver" in selected:
            if self.naver.available():
                try:
                    queries = self.load_queries(limit=query_limit)
                    if not queries:
                        warnings.append("NAVER skipped: no enabled queries in data/news_queries.csv")
                    rows = self.naver.collect(queries, collected_at, target_date, days)
                    raw_items.extend(rows)
                    source_counts["naver"] = len(rows)
                except Exception as exc:  # keep other sources alive
                    warnings.append(f"NAVER collection failed: {exc}")
            else:
                warnings.append("NAVER skipped: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET not set")

        if "policy" in selected:
            try:
                rows = self.policy.collect(target_date, days, collected_at)
                raw_items.extend(rows)
                source_counts["policy"] = len(rows)
            except Exception as exc:
                warnings.append(f"Policy briefing collection failed: {exc}")

        if "dart" in selected:
            if self.dart.available():
                try:
                    rows = self.dart.collect(target_date, days, collected_at)
                    raw_items.extend(rows)
                    source_counts["dart"] = len(rows)
                except Exception as exc:
                    warnings.append(f"OpenDART collection failed: {exc}")
            else:
                warnings.append("OpenDART skipped: OPENDART_API_KEY not set")

        items = self._deduplicate(raw_items)
        schedules: list[ScheduleItem] = []
        if "schedule" in selected:
            lookahead = (
                self.config.schedule_lookahead_days
                if schedule_lookahead_days is None
                else max(schedule_lookahead_days, 0)
            )
            schedules = self.schedule.collect(items, target_date, lookahead_days=lookahead)
            source_counts["schedule"] = len(schedules)
            if not items:
                warnings.append("Schedule extraction found no raw materials; include naver/policy/dart sources")

        return CollectionReport(
            items=items,
            source_counts=source_counts,
            warnings=warnings,
            schedules=schedules,
        )

    def save(self, report: CollectionReport, target_date: date, append_history: bool = True) -> CollectionReport:
        result_dir = self.base_dir / "results" / target_date.strftime("%Y%m%d")
        result_dir.mkdir(parents=True, exist_ok=True)

        snapshot_file = result_dir / "collected_materials.csv"
        self._write_material_csv(snapshot_file, report.items)
        report.snapshot_file = snapshot_file

        schedule_snapshot_file = result_dir / "schedule_candidates.csv"
        self._write_schedule_csv(schedule_snapshot_file, report.schedules)
        report.schedule_snapshot_file = schedule_snapshot_file

        if append_history:
            history_file = self.base_dir / self.config.history_file
            history_file.parent.mkdir(parents=True, exist_ok=True)
            existing_keys = self._read_existing_keys(history_file)
            new_items = [item for item in report.items if item.dedup_key not in existing_keys]
            self._append_material_csv(history_file, new_items)
            report.history_file = history_file

            schedule_history_file = self.base_dir / self.config.schedule_history_file
            schedule_history_file.parent.mkdir(parents=True, exist_ok=True)
            existing_schedule_keys = self._read_existing_keys(schedule_history_file)
            new_schedules = [item for item in report.schedules if item.dedup_key not in existing_schedule_keys]
            self._append_schedule_csv(schedule_history_file, new_schedules)
            report.schedule_history_file = schedule_history_file

        return report

    @staticmethod
    def _deduplicate(items: Iterable[CollectedItem]) -> list[CollectedItem]:
        seen: set[str] = set()
        out: list[CollectedItem] = []
        for item in items:
            if item.dedup_key in seen:
                continue
            seen.add(item.dedup_key)
            out.append(item)
        return out

    @staticmethod
    def _material_fieldnames() -> list[str]:
        return [
            "dedup_key",
            "collected_at",
            "published_at",
            "source_type",
            "source",
            "title",
            "summary",
            "url",
            "query",
            "category",
            "ticker",
            "corp_code",
            "report_code",
            "future_hint",
        ]

    @staticmethod
    def _schedule_fieldnames() -> list[str]:
        return [
            "dedup_key",
            "collected_at",
            "published_at",
            "event_date",
            "event_time",
            "schedule_kind",
            "confidence",
            "source",
            "source_type",
            "title",
            "summary",
            "url",
            "query",
            "category",
            "date_evidence",
        ]

    def _write_material_csv(self, path: Path, items: Iterable[CollectedItem]) -> None:
        self._write_rows(path, self._material_fieldnames(), (item.to_dict() for item in items))

    def _write_schedule_csv(self, path: Path, items: Iterable[ScheduleItem]) -> None:
        self._write_rows(path, self._schedule_fieldnames(), (item.to_dict() for item in items))

    @staticmethod
    def _write_rows(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _append_material_csv(self, path: Path, items: list[CollectedItem]) -> None:
        self._append_rows(path, self._material_fieldnames(), [item.to_dict() for item in items])

    def _append_schedule_csv(self, path: Path, items: list[ScheduleItem]) -> None:
        self._append_rows(path, self._schedule_fieldnames(), [item.to_dict() for item in items])

    def _append_rows(self, path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
        if not rows:
            if not path.exists():
                self._write_rows(path, fieldnames, [])
            return
        write_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for row in rows:
                writer.writerow(row)

    @staticmethod
    def _read_existing_keys(path: Path) -> set[str]:
        if not path.exists() or path.stat().st_size == 0:
            return set()
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            return {str(row.get("dedup_key", "")) for row in csv.DictReader(fp) if row.get("dedup_key")}
