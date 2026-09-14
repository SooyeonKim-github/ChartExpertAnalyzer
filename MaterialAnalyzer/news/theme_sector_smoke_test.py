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

    # V1.2 base 78 themes + focused V1.2.1 live-data extensions.
    assert 85 <= len(catalog.themes) <= 95, len(catalog.themes)
    assert len(catalog.theme_families) >= 10, len(catalog.theme_families)

    bank = classifier.classify(
        title="은행권 3분기 순이자이익 사상 최대 전망",
        summary="대출 성장과 NIM 개선으로 금융지주 실적이 증가할 것으로 예상된다.",
    )
    assert _has_theme(bank, "BANK_EARNINGS"), bank
    bank_theme = _theme(bank, "BANK_EARNINGS")
    assert bank_theme.theme_family == "FINANCE_MACRO"
    assert bank_theme.theme_family_name_ko == "금융·금리"
    assert "FINANCE" in bank_theme.sectors
    assert "BANK" in bank_theme.subsectors
    assert bank_theme.direction == "POSITIVE"

    # Existing-theme recall: the live V1.2 run left this as SECTOR_ONLY.
    drug_approval = classifier.classify(
        title="국내 개발 신약 허가, 환자 치료 선택지 확대",
        summary="국내 개발 의약품이 품목 허가를 획득했다.",
    )
    assert _has_theme(drug_approval, "BIO_APPROVAL"), drug_approval

    # New themes promoted from recurring SECTOR_ONLY patterns.
    data_center_policy = classifier.classify(
        title="AI 데이터센터 특별법 하위법령 마련",
        summary="AI 데이터센터 제도 기반과 지원체계를 구체화한다.",
    )
    assert _has_theme(data_center_policy, "AI_DATA_CENTER_POLICY"), data_center_policy

    physical_ai = classifier.classify(
        title="피지컬 AI로 중소제조 혁신 본격화",
        summary="제조 현장 AI와 로봇 실증을 지원한다.",
    )
    assert _has_theme(physical_ai, "PHYSICAL_AI_POLICY"), physical_ai

    ai_cooperation = classifier.classify(
        title="프랑스와 AI·양자기술 협력 강화",
        summary="인공지능 분야 국제 협력과 공동연구를 확대한다.",
    )
    assert _has_theme(ai_cooperation, "AI_GLOBAL_COOPERATION"), ai_cooperation

    ai_support = classifier.classify(
        title="지역기업 AI 전환 지원 M.AX 사업 확대",
        summary="기업의 AI 도입과 산업 AX 전환을 지원한다.",
    )
    assert _has_theme(ai_support, "AI_INDUSTRY_SUPPORT"), ai_support

    essential_drug = classifier.classify(
        title="필수의약품 공적 공급 확대",
        summary="국가필수의약품의 안정적 공급과 비축을 강화한다.",
    )
    assert _has_theme(essential_drug, "ESSENTIAL_DRUG_SUPPLY"), essential_drug

    renewable_policy = classifier.classify(
        title="정부, 재생에너지 확대 정책 추진",
        summary="재생에너지 보급 목표와 지원 제도를 확대한다.",
    )
    assert _has_theme(renewable_policy, "RENEWABLE_POLICY"), renewable_policy

    solar_support = classifier.classify(
        title="태양광 산업경쟁력 강화위원회 출범",
        summary="태양광 산업 육성과 공급망 경쟁력 강화를 지원한다.",
    )
    assert _has_theme(solar_support, "SOLAR_INDUSTRY_SUPPORT"), solar_support

    housing_finance = classifier.classify(
        title="주택공급 금융지원 대책 발표",
        summary="주택 공급 사업에 대한 금융 지원과 보증을 확대한다.",
    )
    assert _has_theme(housing_finance, "HOUSING_FINANCE_SUPPORT"), housing_finance

    trade_finance = classifier.classify(
        title="중소·중견기업에 무역금융 120조 공급",
        summary="수출기업 정책금융 지원을 확대한다.",
    )
    assert _has_theme(trade_finance, "TRADE_FINANCE_SUPPORT"), trade_finance

    climate_finance = classifier.classify(
        title="기후금융 협업체계 강화",
        summary="녹색금융과 기후투자 지원을 확대한다.",
    )
    assert _has_theme(climate_finance, "CLIMATE_FINANCE"), climate_finance

    # Precision regressions discovered from the V1.2 live report.
    medical_content = classifier.classify(
        title="안전한 어린이 의약정보 콘텐츠 공모전 개최",
        summary="어린이에게 올바른 의약품 정보를 제공하기 위한 공모전이다.",
    )
    assert not any(
        item.sector == "ENTERTAINMENT_MEDIA" for item in medical_content.sectors
    ), medical_content

    quantum_development = classifier.classify(
        title="국회에서 양자 분야 발전방향 논의",
        summary="양자기술 산업의 중장기 발전 방향을 논의했다.",
    )
    assert not any(
        item.sector == "POWER_ENERGY" for item in quantum_development.sectors
    ), quantum_development

    consumer_agency = classifier.classify(
        title="한국소비자원, 온라인 거래 피해 예방 정보 제공",
        summary="소비자 피해 예방을 위한 안내자료를 배포했다.",
    )
    assert not any(
        item.sector == "CONSUMER_RETAIL" for item in consumer_agency.sectors
    ), consumer_agency

    # V1.2 precision protections must remain intact.
    household_debt = classifier.classify(
        title="2026년 8월 가계대출 동향(잠정) 및 가계부채 점검회의 개최",
        summary="가계대출 증가폭과 금융권 관리 현황을 점검했다.",
        body="과거 기준금리 인상과 시장금리 상승기의 대출 흐름도 함께 점검했다.",
    )
    assert not _has_theme(household_debt, "RATE_HIKE"), household_debt

    domestic_smr = classifier.classify(
        title="소형모듈원자로(SMR) 개발·상용화, 특별법·시행령 시행으로 본격화",
        summary="국내 SMR 기술개발과 제도 기반을 마련한다.",
    )
    assert _has_theme(domestic_smr, "NUCLEAR_POLICY"), domestic_smr
    assert not _has_theme(domestic_smr, "NUCLEAR_EXPORT"), domestic_smr

    generic_export_control = classifier.classify(
        title="제1차 한-베트남 수출통제대화 개최, 공급망 안정 및 현지 진출기업 지원 강화",
        summary="양국 수출통제 제도와 기업 애로사항을 논의했다.",
    )
    assert not _has_theme(
        generic_export_control, "SEMICONDUCTOR_EXPORT_RESTRICTION"
    ), generic_export_control

    unrelated = classifier.classify(
        title="정례 위원회 개최 결과 안내",
        summary="위원회는 예정된 안건을 논의했다.",
    )
    assert not unrelated.themes, unrelated

    sample_row = {
        "market_date": "20260914",
        "classification_type": "THEME",
        "cluster_id": "CL_TEST",
        "representative_title": "은행권 3분기 순이자이익 사상 최대 전망",
        "theme_family": bank_theme.theme_family,
        "theme_family_name_ko": bank_theme.theme_family_name_ko,
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
        assert "theme_family" in detail.read_text(encoding="utf-8-sig").splitlines()[0]
        assert "theme_family" in summary.read_text(encoding="utf-8-sig").splitlines()[0]

    print("ThemeSectorAnalyzer V1.2.1 smoke test: OK")
    print(f"sector_count       = {len(catalog.sectors)}")
    print(f"theme_family_count = {len(catalog.theme_families)}")
    print(f"theme_count        = {len(catalog.themes)}")


def _has_theme(result, theme: str) -> bool:
    return any(item.theme == theme for item in result.themes)


def _theme(result, theme: str):
    return next(item for item in result.themes if item.theme == theme)


if __name__ == "__main__":
    main()
