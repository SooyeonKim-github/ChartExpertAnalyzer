from __future__ import annotations

from datetime import date
from pathlib import Path

from MaterialAnalyzer.analyzers.schedule_importance import ScheduleImportanceAnalyzer
from MaterialAnalyzer.mapping.theme_mapper import ThemeMapper
from MaterialAnalyzer.mapping.theme_stock_mapper import ThemeStockMapper
from MaterialAnalyzer.schedule_analysis import ScheduleAnalysisEngine
from MaterialAnalyzer.schedule_models import ScheduleItem


def _schedule(title: str, summary: str = "") -> ScheduleItem:
    return ScheduleItem(
        collected_at="2026-09-02T20:00:00+09:00",
        published_at="2026-09-02T10:00:00+09:00",
        event_date="2026-09-05",
        event_time="14:00",
        schedule_kind="정책발표",
        confidence=0.95,
        source="test",
        source_type="news",
        title=title,
        summary=summary,
        url="https://example.com/a",
        query="AI 투자",
        category="policy",
        date_evidence="9월 5일",
    )


def test_theme_mapper_and_stock_mapper(tmp_path: Path) -> None:
    keyword_file = tmp_path / "themes.csv"
    keyword_file.write_text(
        "theme,keywords,enabled\nAI반도체,AI 반도체|HBM,1\n원전,원전|SMR,1\n",
        encoding="utf-8-sig",
    )
    stock_file = tmp_path / "stocks.csv"
    stock_file.write_text(
        "theme,ticker,name,relevance,relation_type,reason,enabled\n"
        "AI반도체,000660,테스트반도체,0.92,DIRECT,테스트,1\n",
        encoding="utf-8-sig",
    )

    themes = ThemeMapper(keyword_file).map(_schedule("정부 AI 반도체 HBM 투자 전략 발표"))
    assert themes[0].theme == "AI반도체"
    assert themes[0].confidence >= 0.9

    stocks = ThemeStockMapper(stock_file).map("AI반도체")
    assert stocks[0].ticker == "000660"
    assert stocks[0].stock_theme_score == 92.0


def test_importance_scores_money_and_authority() -> None:
    analyzer = ScheduleImportanceAnalyzer()
    result = analyzer.analyze(
        _schedule("정부, AI 반도체 10조원 투자계획 발표 예정"),
        date(2026, 9, 2),
        [],
    )

    assert result.authority_score >= 13
    assert result.money_score >= 13
    assert result.money_amount_krw == 10_000_000_000_000
    assert result.novelty_status == "INSUFFICIENT_HISTORY"


def test_engine_preserves_unmapped_schedule(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "theme_keywords.csv").write_text("theme,keywords,enabled\n", encoding="utf-8-sig")
    (data_dir / "theme_stocks.csv").write_text(
        "theme,ticker,name,relevance,relation_type,reason,enabled\n",
        encoding="utf-8-sig",
    )

    engine = ScheduleAnalysisEngine(base_dir=tmp_path)
    rows = engine.analyze([_schedule("정부 산업정책 발표 예정")], date(2026, 9, 2))

    assert len(rows) == 1
    assert rows[0].theme == ""
    assert rows[0].ticker == ""
    assert "UNMAPPED" in rows[0].reason
