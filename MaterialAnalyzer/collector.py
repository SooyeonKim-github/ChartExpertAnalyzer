from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .collectors import NaverNewsCollector, OpenDartCollector, PolicyBriefingCollector
from .config import DEFAULT_CONFIG, MaterialCollectorConfig
from .models import CollectedItem


@dataclass
class CollectionReport:
    items: list[CollectedItem]
    source_counts: dict[str, int]
    warnings: list[str]
    snapshot_file: Path | None = None
    history_file: Path | None = None


class MaterialCollector:
    """Collect raw catalyst candidates without assigning investment scores.

    V1 intentionally keeps collection separate from material analysis. This prevents
    collection-source changes from silently altering scoring logic later.
    """

    def __init__(self, config: MaterialCollectorConfig = DEFAULT_CONFIG, base_dir: Path | None = None) -> None:
        self.config = config
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.naver = NaverNewsCollector(config)
        self.dart = OpenDartCollector(config)
        self.policy = PolicyBriefingCollector(config)

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
        sources: Iterable[str] = ("naver", "policy", "dart"),
        query_limit: int | None = None,
    ) -> CollectionReport:
        selected = {s.strip().lower() for s in sources if s.strip()}
        collected_at = datetime.now().astimezone().isoformat()
        raw_items: list[CollectedItem] = []
        warnings: list[str] = []
        source_counts: dict[str, int] = {}

        if "naver" in selected:
            if self.naver.available():
                try:
                    queries = self.load_queries(limit=query_limit)
                    rows = self.naver.collect(queries, collected_at)
                    raw_items.extend(rows)
                    source_counts["naver"] = len(rows)
                except Exception as exc:  # keep other sources alive
                    warnings.append(f"NAVER collection failed: {exc}")
            else:
                warnings.append("NAVER skipped: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET not set")

        if "policy" in selected:
            try:
                rows = self.policy.collect(collected_at)
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
        return CollectionReport(items=items, source_counts=source_counts, warnings=warnings)

    def save(self, report: CollectionReport, target_date: date, append_history: bool = True) -> CollectionReport:
        result_dir = self.base_dir / "results" / target_date.strftime("%Y%m%d")
        result_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = result_dir / "collected_materials.csv"
        self._write_csv(snapshot_file, report.items)
        report.snapshot_file = snapshot_file

        if append_history:
            history_file = self.base_dir / self.config.history_file
            history_file.parent.mkdir(parents=True, exist_ok=True)
            existing_keys = self._read_existing_keys(history_file)
            new_items = [item for item in report.items if item.dedup_key not in existing_keys]
            self._append_csv(history_file, new_items)
            report.history_file = history_file

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
    def _fieldnames() -> list[str]:
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

    def _write_csv(self, path: Path, items: Iterable[CollectedItem]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=self._fieldnames())
            writer.writeheader()
            for item in items:
                writer.writerow(item.to_dict())

    def _append_csv(self, path: Path, items: list[CollectedItem]) -> None:
        if not items:
            if not path.exists():
                self._write_csv(path, [])
            return
        write_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=self._fieldnames())
            if write_header:
                writer.writeheader()
            for item in items:
                writer.writerow(item.to_dict())

    @staticmethod
    def _read_existing_keys(path: Path) -> set[str]:
        if not path.exists() or path.stat().st_size == 0:
            return set()
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            return {str(row.get("dedup_key", "")) for row in csv.DictReader(fp) if row.get("dedup_key")}
