from __future__ import annotations

from datetime import date

from MaterialAnalyzer.collectors.schedule import ScheduleCollector
from MaterialAnalyzer.config import DEFAULT_CONFIG
from MaterialAnalyzer.models import CollectedItem


def _material(title: str, summary: str = "") -> CollectedItem:
    return CollectedItem(
        collected_at="2026-09-02T20:00:00+09:00",
        published_at="2026-09-02T10:00:00+09:00",
        source_type="news",
        source="test",
        title=title,
        summary=summary,
        url="https://example.com/schedule",
        future_hint=True,
    )


def test_extract_absolute_schedule_with_time() -> None:
    collector = ScheduleCollector(DEFAULT_CONFIG)
    rows = collector.collect(
        [_material("정부, 9월 5일 오후 2시 AI 정책 발표 예정")],
        date(2026, 9, 2),
        lookahead_days=21,
    )

    assert len(rows) == 1
    assert rows[0].event_date == "2026-09-05"
    assert rows[0].event_time == "14:00"
    assert rows[0].schedule_kind == "정책발표"
    assert rows[0].confidence >= 0.9


def test_extract_relative_schedule() -> None:
    collector = ScheduleCollector(DEFAULT_CONFIG)
    rows = collector.collect(
        [_material("내일 오전 10시 자율주행 업계 간담회 개최")],
        date(2026, 9, 2),
        lookahead_days=7,
    )

    assert len(rows) == 1
    assert rows[0].event_date == "2026-09-03"
    assert rows[0].event_time == "10:00"
    assert rows[0].schedule_kind == "간담회"


def test_reject_schedule_without_resolvable_date() -> None:
    collector = ScheduleCollector(DEFAULT_CONFIG)
    rows = collector.collect(
        [_material("정부, 로봇 산업 육성 계획 추진")],
        date(2026, 9, 2),
        lookahead_days=21,
    )

    assert rows == []


def test_reject_date_outside_lookahead() -> None:
    collector = ScheduleCollector(DEFAULT_CONFIG)
    rows = collector.collect(
        [_material("정부, 10월 20일 탄소중립 공청회 개최")],
        date(2026, 9, 2),
        lookahead_days=21,
    )

    assert rows == []


def test_same_article_can_expose_multiple_event_dates() -> None:
    collector = ScheduleCollector(DEFAULT_CONFIG)
    rows = collector.collect(
        [_material("대통령 순방 주요일정", "9월 4일 정상회담, 9월 5일 비즈니스 간담회 개최")],
        date(2026, 9, 2),
        lookahead_days=7,
    )

    assert [row.event_date for row in rows] == ["2026-09-04", "2026-09-05"]
