from __future__ import annotations

from datetime import date
from pathlib import Path

from MaterialAnalyzer.collector import CollectionReport, MaterialCollector
from MaterialAnalyzer.models import CollectedItem


def _item(url: str, title: str = "정부 AI 투자 발표") -> CollectedItem:
    return CollectedItem(
        collected_at="2026-09-02T20:00:00+09:00",
        published_at="2026-09-02",
        source_type="news",
        source="test",
        title=title,
        summary="내년 투자 계획 발표 예정",
        url=url,
        future_hint=True,
    )


def test_deduplicate_same_url() -> None:
    rows = MaterialCollector._deduplicate([_item("https://example.com/a"), _item("https://example.com/a")])
    assert len(rows) == 1


def test_save_snapshot_and_history_without_duplicate(tmp_path: Path) -> None:
    collector = MaterialCollector(base_dir=tmp_path)
    item = _item("https://example.com/a")
    report = CollectionReport(items=[item], source_counts={"test": 1}, warnings=[])

    collector.save(report, date(2026, 9, 2), append_history=True)
    collector.save(report, date(2026, 9, 2), append_history=True)

    snapshot = tmp_path / "results" / "20260902" / "collected_materials.csv"
    history = tmp_path / "data" / "material_items.csv"
    assert snapshot.exists()
    assert history.exists()

    lines = history.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) == 2  # header + one unique item
