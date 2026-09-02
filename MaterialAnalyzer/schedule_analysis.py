from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .analysis_models import ScheduleAnalysisRow
from .analyzers import ScheduleImportanceAnalyzer
from .mapping import ThemeMapper, ThemeStockMapper
from .schedule_models import ScheduleItem


class ScheduleAnalysisEngine:
    """Analyze schedule candidates and expand them into theme/stock rows."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.theme_mapper = ThemeMapper(self.base_dir / "data" / "theme_keywords.csv")
        self.stock_mapper = ThemeStockMapper(self.base_dir / "data" / "theme_stocks.csv")
        self.importance = ScheduleImportanceAnalyzer(self.base_dir / "data" / "material_items.csv")

    def analyze_date(self, scan_date: date) -> tuple[list[ScheduleAnalysisRow], Path]:
        result_dir = self.base_dir / "results" / scan_date.strftime("%Y%m%d")
        schedule_file = result_dir / "schedule_candidates.csv"
        schedules = self.load_schedules(schedule_file)
        rows = self.analyze(schedules, scan_date)
        output = result_dir / "schedule_analysis.csv"
        output.parent.mkdir(parents=True, exist_ok=True)
        self.write_csv(output, rows)
        return rows, output

    def analyze(self, schedules: list[ScheduleItem], scan_date: date) -> list[ScheduleAnalysisRow]:
        out: list[ScheduleAnalysisRow] = []

        for schedule in schedules:
            theme_matches = self.theme_mapper.map(schedule)
            importance = self.importance.analyze(schedule, scan_date, theme_matches)

            if not theme_matches:
                out.append(self._row(schedule, scan_date, importance, None, None))
                continue

            for theme in theme_matches:
                stocks = self.stock_mapper.map(theme.theme)
                if not stocks:
                    out.append(self._row(schedule, scan_date, importance, theme, None))
                    continue
                for stock in stocks:
                    out.append(self._row(schedule, scan_date, importance, theme, stock))

        out.sort(
            key=lambda row: (
                -row.schedule_score,
                row.event_date,
                -row.theme_confidence,
                -(row.stock_theme_score or 0.0),
                row.ticker,
            )
        )
        return out

    @staticmethod
    def _row(schedule, scan_date, importance, theme, stock) -> ScheduleAnalysisRow:
        reason_parts = [importance.reason]
        if theme is not None:
            reason_parts.append(
                f"theme={theme.theme} conf={theme.confidence:.2f} keywords={','.join(theme.matched_keywords)}"
            )
        else:
            reason_parts.append("theme=UNMAPPED")
        if stock is not None:
            reason_parts.append(
                f"stock={stock.name} relevance={stock.relevance:.2f} relation={stock.relation_type}"
            )
            if stock.reason:
                reason_parts.append(stock.reason)

        return ScheduleAnalysisRow(
            scan_date=scan_date.strftime("%Y%m%d"),
            event_date=schedule.event_date,
            event_time=schedule.event_time,
            schedule_kind=schedule.schedule_kind,
            title=schedule.title,
            schedule_score=importance.schedule_score,
            priority=importance.priority,
            authority_score=importance.authority_score,
            novelty_score=importance.novelty_score,
            money_score=importance.money_score,
            policy_score=importance.policy_score,
            theme_clarity_score=importance.theme_clarity_score,
            event_certainty_score=importance.event_certainty_score,
            novelty_status=importance.novelty_status,
            similar_history_count=importance.similar_history_count,
            money_amount_krw=importance.money_amount_krw,
            theme=theme.theme if theme else "",
            theme_confidence=theme.confidence if theme else 0.0,
            theme_match_type=theme.match_type if theme else "",
            matched_keywords="|".join(theme.matched_keywords) if theme else "",
            ticker=stock.ticker if stock else "",
            name=stock.name if stock else "",
            stock_theme_score=stock.stock_theme_score if stock else None,
            relation_type=stock.relation_type if stock else "",
            reason="; ".join(reason_parts),
            source=schedule.source,
            url=schedule.url,
        )

    @staticmethod
    def load_schedules(path: Path) -> list[ScheduleItem]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        out: list[ScheduleItem] = []
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                try:
                    confidence = float(row.get("confidence", 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0
                out.append(
                    ScheduleItem(
                        collected_at=str(row.get("collected_at", "")),
                        published_at=str(row.get("published_at", "")),
                        event_date=str(row.get("event_date", "")),
                        event_time=str(row.get("event_time", "")),
                        schedule_kind=str(row.get("schedule_kind", "")),
                        confidence=confidence,
                        source=str(row.get("source", "")),
                        source_type=str(row.get("source_type", "")),
                        title=str(row.get("title", "")),
                        summary=str(row.get("summary", "")),
                        url=str(row.get("url", "")),
                        query=str(row.get("query", "")),
                        category=str(row.get("category", "")),
                        date_evidence=str(row.get("date_evidence", "")),
                    )
                )
        return out

    @staticmethod
    def fieldnames() -> list[str]:
        return list(ScheduleAnalysisRow.__dataclass_fields__.keys())

    def write_csv(self, path: Path, rows: list[ScheduleAnalysisRow]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=self.fieldnames())
            writer.writeheader()
            for row in rows:
                writer.writerow(row.to_dict())
