from __future__ import annotations

import json
import re
from collections import Counter


STRONG_MATERIAL_RE = re.compile(
    r"단일판매|공급계약|수주|유상증자|무상증자|전환사채|신주인수권부사채|교환사채|"
    r"전환청구권행사|신주인수권행사|교환청구권행사|전환가액.*조정|행사가액.*조정|교환가액.*조정|"
    r"신규시설|시설투자|설비투자|타법인.*주식|주식.*취득|주식.*처분|합병|분할|"
    r"영업양수|영업양도|유형자산.*양수|유형자산.*양도|자산양수|자산양도|"
    r"자기주식.*취득|자기주식.*처분|자기주식.*소각|자사주.*처분|소각결정|"
    r"현금.*배당|최대주주.*변경|소송|가처분|거래정지|상장폐지|관리종목|영업정지|"
    r"회생|파산|잠정.*실적|영업.*실적|매출액.*손익|기업가치제고|"
    r"감자결정|주식병합|주식분할|금전대여|단기차입|자금차입|채무보증|담보제공|"
    r"파생상품.*손실|투자판단관련주요경영사항|기술이전|임상|품목허가|"
    r"공개매수|경영권|증권발행결과|신탁계약해지결과|신탁계약에의한취득상황",
    re.I,
)

# Historical raw rows are always retained. These patterns only keep repetitive / low-impact
# administrative disclosures out of ArticleCluster and downstream scoring/backtests.
ROUTINE_RE = re.compile(
    r"임원.?주요주주특정증권등소유상황보고서|주식등의대량보유상황보고서|"
    r"최대주주등소유주식변동신고서|임원.?주요주주특정증권등거래계획보고서|"
    r"증권발행실적보고서|투자설명서|효력발생안내|일괄신고서|일괄신고추가서류|"
    r"주주명부.*기준일|주주명부폐쇄|주주총회소집결의|주주총회소집공고|"
    r"정기주주총회결과|주주총회집중일.*개최사유|의결권대리행사권유|"
    r"독립이사.*선임|독립이사.*해임|기업지배구조보고서|대규모기업집단현황공시|"
    r"사업보고서|반기보고서|분기보고서|연결감사보고서|감사보고서|감사보고서제출|"
    r"주식매수선택권.*부여|지급수단별.*지급금액|결산실적공시예고|"
    r"동일인등출자계열회사와의상품.?용역거래|본점소재지변경|상호변경안내|"
    r"공정거래자율준수프로그램운영현황|특수관계인과의내부거래|"
    r"약관에의한금융거래시계열금융회사|계열금융회사의약관에의한금융거래|"
    r"부동산투자회사부동산임대",
    re.I,
)


def classify_dart_analysis(title: str, stock_code: str) -> str:
    title = str(title or "").strip()
    stock_code = str(stock_code or "").strip()
    # Historical backtests only target listed shares. Keep every raw row, but do not
    # spend clustering time on company disclosures that cannot resolve to a listed ticker.
    if not stock_code:
        return "SKIP_HISTORY_NONLISTED"
    # Strong catalysts always survive the routine filter, including correction reports
    # whose title still contains the underlying material disclosure type.
    if STRONG_MATERIAL_RE.search(title):
        return "PENDING"
    if ROUTINE_RE.search(title):
        return "SKIP_HISTORY_ROUTINE"
    return "PENDING"


def _stock_code_from_metadata(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return ""
    return str(payload.get("stock_code", "") or "").strip()


def refresh_existing_dart_prefilter(database) -> dict[str, int]:
    """Reclassify already collected DART rows so resumed history gains current filtering."""
    conn = database.connect()
    try:
        rows = conn.execute(
            "SELECT article_id,title,analysis_status,source_metadata_json FROM articles WHERE source_id='DART'"
        ).fetchall()
        updates = []
        counts = Counter()
        for row in rows:
            status = classify_dart_analysis(
                row["title"],
                _stock_code_from_metadata(row["source_metadata_json"]),
            )
            counts[status] += 1
            if (row["analysis_status"] or "PENDING") != status:
                updates.append((status, row["article_id"]))
        if updates:
            conn.executemany(
                "UPDATE articles SET analysis_status=?, updated_db_at=CURRENT_TIMESTAMP WHERE article_id=?",
                updates,
            )
            conn.commit()
        counts["UPDATED_ROWS"] = len(updates)
        counts["TOTAL_ROWS"] = len(rows)
        return dict(counts)
    finally:
        conn.close()
