from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Iterable

from ..config import MaterialCollectorConfig
from ..models import CollectedItem
from ..schedule_models import ScheduleItem


_KOREAN_DATE_RE = re.compile(r"(?:(20\d{2})년\s*)?(\d{1,2})월\s*(\d{1,2})일")
_NUMERIC_DATE_RE = re.compile(r"(?:(20\d{2})[./-]\s*)?(\d{1,2})[./-]\s*(\d{1,2})(?:일)?")
_COMING_DAY_RE = re.compile(r"오는\s*(\d{1,2})일")
_NEXT_MONTH_DAY_RE = re.compile(r"다음\s*달\s*(\d{1,2})일")
_BARE_DAY_RE = re.compile(r"(?<![\d월./-])(\d{1,2})일(?!\s*(?:간|동안|째|전|후))")
_TIME_RE = re.compile(r"(?:(오전|오후)\s*)?(\d{1,2})시(?:\s*(\d{1,2})분)?")
_CLOCK_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")

_WEEKDAYS = {
    "월": 0,
    "화": 1,
    "수": 2,
    "목": 3,
    "금": 4,
    "토": 5,
    "일": 6,
}
_WEEKDAY_RE = re.compile(r"(?:(이번\s*주|다음\s*주|오는)\s*)?([월화수목금토일])요일")

_KIND_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("정상회담", ("정상회담", "정상 회담")),
    ("공청회", ("공청회",)),
    ("간담회", ("간담회", "라운드테이블")),
    ("실적발표", ("실적 발표", "실적발표", "잠정실적")),
    ("통계발표", ("인구동향", "고용동향", "물가동향", "산업활동동향", "수출입동향", "소비자물가")),
    ("정책발표", ("정책 발표", "대책 발표", "방안 발표", "로드맵 발표", "전략 발표")),
    ("회의", ("회의", "협의회", "위원회")),
    ("방문", ("방문", "순방")),
    ("상장", ("상장", "증권신고서")),
    ("출시", ("출시", "공개 예정", "공개한다")),
    ("착공", ("착공", "준공")),
    ("시행", ("시행", "시행령", "시행규칙")),
    ("의결", ("의결", "심의")),
    ("행사", ("행사", "컨퍼런스", "박람회", "포럼", "세미나")),
    ("발표", ("발표", "공개")),
)


class ScheduleCollector:
    """Extract future event schedules from collected material text.

    This stage intentionally requires both a schedule-like keyword and a resolvable
    event date. It is designed around the lecture workflow: prepare known future
    events first, then observe whether the related stocks actually react.
    """

    source_name = "schedule_extractor"

    def __init__(self, config: MaterialCollectorConfig) -> None:
        self.config = config

    def collect(
        self,
        items: Iterable[CollectedItem],
        target_date: date,
        lookahead_days: int = 21,
    ) -> list[ScheduleItem]:
        end_date = target_date + timedelta(days=max(lookahead_days, 0))
        out: list[ScheduleItem] = []

        for item in items:
            text = f"{item.title} {item.summary}".strip()
            if not text or not self._looks_like_schedule(text):
                continue

            kind = self._classify_kind(text)
            event_time = self._extract_time(text)
            dates = self._extract_dates(text, target_date)
            if not dates:
                continue

            for event_day, evidence, confidence in dates:
                if event_day < target_date or event_day > end_date:
                    continue
                out.append(
                    ScheduleItem(
                        collected_at=item.collected_at,
                        published_at=item.published_at,
                        event_date=event_day.isoformat(),
                        event_time=event_time,
                        schedule_kind=kind,
                        confidence=confidence,
                        source=item.source,
                        source_type=item.source_type,
                        title=item.title,
                        summary=item.summary,
                        url=item.url,
                        query=item.query,
                        category=item.category,
                        date_evidence=evidence,
                    )
                )

        return self._deduplicate(out)

    def _looks_like_schedule(self, text: str) -> bool:
        return any(keyword in text for keyword in self.config.future_hint_keywords)

    @staticmethod
    def _classify_kind(text: str) -> str:
        for kind, patterns in _KIND_PATTERNS:
            if any(pattern in text for pattern in patterns):
                return kind
        return "기타일정"

    @staticmethod
    def _extract_time(text: str) -> str:
        match = _TIME_RE.search(text)
        if match:
            ampm, hour_raw, minute_raw = match.groups()
            hour = int(hour_raw)
            minute = int(minute_raw or 0)
            if ampm == "오후" and hour < 12:
                hour += 12
            elif ampm == "오전" and hour == 12:
                hour = 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"

        match = _CLOCK_RE.search(text)
        if match:
            return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
        return ""

    def _extract_dates(self, text: str, target_date: date) -> list[tuple[date, str, float]]:
        candidates: list[tuple[date, str, float]] = []

        relative = (
            ("오늘", 0, 0.88),
            ("내일", 1, 0.9),
            ("모레", 2, 0.9),
        )
        for token, offset, confidence in relative:
            if token in text:
                candidates.append((target_date + timedelta(days=offset), token, confidence))

        for match in _KOREAN_DATE_RE.finditer(text):
            year_raw, month_raw, day_raw = match.groups()
            resolved = self._safe_date(
                int(year_raw) if year_raw else target_date.year,
                int(month_raw),
                int(day_raw),
                target_date,
                explicit_year=bool(year_raw),
            )
            if resolved:
                candidates.append((resolved, match.group(0), 0.98 if year_raw else 0.95))

        for match in _NUMERIC_DATE_RE.finditer(text):
            year_raw, month_raw, day_raw = match.groups()
            resolved = self._safe_date(
                int(year_raw) if year_raw else target_date.year,
                int(month_raw),
                int(day_raw),
                target_date,
                explicit_year=bool(year_raw),
            )
            if resolved:
                candidates.append((resolved, match.group(0), 0.96 if year_raw else 0.9))

        for match in _COMING_DAY_RE.finditer(text):
            resolved = self._day_in_current_or_next_month(target_date, int(match.group(1)))
            if resolved:
                candidates.append((resolved, match.group(0), 0.88))

        for match in _NEXT_MONTH_DAY_RE.finditer(text):
            month = 1 if target_date.month == 12 else target_date.month + 1
            year = target_date.year + 1 if target_date.month == 12 else target_date.year
            try:
                resolved = date(year, month, int(match.group(1)))
            except ValueError:
                resolved = None
            if resolved:
                candidates.append((resolved, match.group(0), 0.9))

        for match in _BARE_DAY_RE.finditer(text):
            resolved = self._day_in_current_or_next_month(target_date, int(match.group(1)))
            if resolved:
                candidates.append((resolved, match.group(0), 0.76))

        for match in _WEEKDAY_RE.finditer(text):
            modifier, weekday_char = match.groups()
            weekday = _WEEKDAYS[weekday_char]
            delta = (weekday - target_date.weekday()) % 7
            normalized_modifier = (modifier or "").replace(" ", "")
            if "다음" in normalized_modifier:
                delta += 7
            elif normalized_modifier == "오는" and delta == 0:
                delta = 7
            resolved = target_date + timedelta(days=delta)
            candidates.append((resolved, match.group(0), 0.78))

        best_by_day: dict[date, tuple[str, float]] = {}
        for resolved, evidence, confidence in candidates:
            previous = best_by_day.get(resolved)
            if previous is None or confidence > previous[1]:
                best_by_day[resolved] = (evidence, confidence)

        return [
            (resolved, evidence, confidence)
            for resolved, (evidence, confidence) in sorted(best_by_day.items(), key=lambda row: row[0])
        ]

    @staticmethod
    def _safe_date(
        year: int,
        month: int,
        day: int,
        target_date: date,
        explicit_year: bool,
    ) -> date | None:
        try:
            resolved = date(year, month, day)
        except ValueError:
            return None

        if not explicit_year and resolved < target_date - timedelta(days=7):
            try:
                resolved = date(year + 1, month, day)
            except ValueError:
                return None
        return resolved

    @staticmethod
    def _day_in_current_or_next_month(target_date: date, day: int) -> date | None:
        try:
            current = date(target_date.year, target_date.month, day)
        except ValueError:
            current = None
        if current is not None and current >= target_date:
            return current

        next_month = 1 if target_date.month == 12 else target_date.month + 1
        next_year = target_date.year + 1 if target_date.month == 12 else target_date.year
        try:
            return date(next_year, next_month, day)
        except ValueError:
            return None

    @staticmethod
    def _deduplicate(items: Iterable[ScheduleItem]) -> list[ScheduleItem]:
        seen: set[str] = set()
        out: list[ScheduleItem] = []
        for item in items:
            if item.dedup_key in seen:
                continue
            seen.add(item.dedup_key)
            out.append(item)
        return out
