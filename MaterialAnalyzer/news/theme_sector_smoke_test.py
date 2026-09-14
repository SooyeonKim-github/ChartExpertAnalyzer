from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .theme_sector import MasterCatalog, RuleClassifier, ThemeSectorReporter


ROOT = Path(__file__).resolve().parents[1]
SECTOR_MASTER = ROOT / "data" / "reference" / "sector_master.yaml"
THEME_MASTER = ROOT / "data" / "reference" / "theme_master.yaml"


def main() -> None:
    catalog = MasterCatalog.load(SECTOR_MASTER, THEME_MASTER)
    classifier = RuleClassifier(catalog)

    bank = classifier.classify(
        title="은행권 3분기 순이자이익 사상 최대 전망",
        summary="대출 성장과 NIM 개선으로 금융지주 실적이 증가할 것으로 예상된다.",
    )
    assert _has_theme(bank, "BANK_EARNINGS"), bank
    bank_theme = _theme(bank, "BANK_EARNINGS")
    assert "FINANCE" in bank_theme.sectors
    assert "BANK" in bank_theme.subsectors
    assert bank_theme.direction == "POSITIVE"

    data_center = classifier.classify(
        title="정부, AI 데이터센터 투자 확대 추진",
        summary="GPU 서버와 전력 인프라 구축을 위한 대규모 데이터센터 증설 계획",
    )
    assert _has_theme(data_center, "AI_DATA_CENTER_INVESTMENT"), data_center
    dc_theme = _theme(data_center, "AI_DATA_CENTER_INVESTMENT")
    assert {"AI_IT", "SEMICONDUCTOR", "POWER_ENERGY"}.issubset(set(dc_theme.sectors))

    steel = classifier.classify(
        title="미국, 한국산 철강 관세 부과·규제 강화",
        summary="수입 철강 제품에 대한 무역규제를 강화한다.",
    )
    assert _has_theme(steel, "STEEL_TARIFF"), steel
    assert _theme(steel, "STEEL_TARIFF").direction == "NEGATIVE"

    # Regression: household-debt releases can mention historical rate hikes deep in
    # the body. RATE_HIKE must be explicit in title/summary, not body-only evidence.
    household_debt = classifier.classify(
        title="2026년 8월 가계대출 동향(잠정) 및 가계부채 점검회의 개최",
        summary="가계대출 증가폭과 금융권 관리 현황을 점검했다.",
        body="과거 기준금리 인상과 시장금리 상승기의 대출 흐름도 함께 점검했다.",
    )
    assert not _has_theme(household_debt, "RATE_HIKE"), household_debt

    # Regression: domestic SMR legislation is nuclear-sector material, but it is not
    # an export catalyst unless export/order/overseas context is explicit.
    domestic_smr = classifier.classify(
        title="소형모듈원자로(SMR) 개발·상용화, 특별법·시행령 시행으로 본격화",
        summary="국내 SMR 기술개발과 제도 기반을 마련한다.",
    )
    assert not _has_theme(domestic_smr, "NUCLEAR_EXPORT"), domestic_smr
    assert any(item.sector == "POWER_ENERGY" for item in domestic_smr.sectors), domestic_smr

    nuclear_export = classifier.classify(
        title="한국형 원전 체코 수출 프로젝트 계약 협상 본격화",
        summary="해외 원전 수주와 계약 절차가 진행 중이다.",
    )
    assert _has_theme(nuclear_export, "NUCLEAR_EXPORT"), nuclear_export

    # Regression: generic export-control dialogue is not automatically a
    # semiconductor export restriction. Semiconductor/AI-chip context is required.
    generic_export_control = classifier.classify(
        title="제1차 한-베트남 수출통제대화 개최, 공급망 안정 및 현지 진출기업 지원 강화",
        summary="양국 수출통제 제도와 기업 애로사항을 논의했다.",
    )
    assert not _has_theme(
        generic_export_control, "SEMICONDUCTOR_EXPORT_RESTRICTION"
    ), generic_export_control

    semiconductor_export_control = classifier.classify(
        title="미국, AI칩·반도체 장비 수출통제 강화",
        summary="첨단 반도체와 GPU 장비의 수출 제한을 확대한다.",
    )
    assert _has_theme(
        semiconductor_export_control, "SEMICONDUCTOR_EXPORT_RESTRICTION"
    ), semiconductor_export_control

    unrelated = classifier.classify(
        title="정례 위원회 개최 결과 안내",
        summary="위원회는 예정된 안건을 논의했다.",
    )
    assert not unrelated.themes, unrelated

    # Report contract smoke check: UTF-8 CSV headers and both output formats.
    sample_row = {
        "market_date": "20260914",
        "classification_type": "THEME",
        "cluster_id": "CL_TEST",
        "representative_title": "은행권 3분기 순이자이익 사상 최대 전망",
        "theme": bank_theme.theme,
        "theme_name_ko": bank_theme.theme_name_ko,
        "sectors": "|".join(bank_theme.sectors),
        "sector_names_ko": "|".join(bank_theme.sector_names_ko),
        "subsectors": "|".join(bank_theme.subsectors),
        "subsector_names_ko": "|".join(bank_theme.subsector_names_ko),
        "direction": bank_theme.direction,
        "rule_score": bank_theme.rule_score,
        "confidence": bank_theme.confidence,
        "matched_keywords": "|".join(bank_theme.matched_keywords),
        "article_count": 2,
        "source_count": 2,
    }
    with TemporaryDirectory() as temp_dir:
        detail = Path(temp_dir) / "detail.csv"
        summary = Path(temp_dir) / "summary.csv"
        ThemeSectorReporter.export_detail([sample_row], detail)
        ThemeSectorReporter.export_daily_summary([sample_row], summary)
        assert detail.exists() and detail.stat().st_size > 0
        assert summary.exists() and summary.stat().st_size > 0

    print("ThemeSectorAnalyzer V1 precision smoke test: OK")
    print(f"sector_count = {len(catalog.sectors)}")
    print(f"theme_count  = {len(catalog.themes)}")


def _has_theme(result, theme: str) -> bool:
    return any(item.theme == theme for item in result.themes)


def _theme(result, theme: str):
    return next(item for item in result.themes if item.theme == theme)


if __name__ == "__main__":
    main()
