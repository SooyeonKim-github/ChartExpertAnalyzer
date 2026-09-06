from __future__ import annotations

import json
import re
from collections import Counter


STRONG_MATERIAL_RE = re.compile(
    r"단일판매|공급계약|수주|유상증자|무상증자|전환사채|신주인수권부사채|교환사채|"
    r"신규시설|시설투자|설비투자|타법인.*주식|주식.*취득|주식.*처분|합병|분할|"
    r"영업양수|영업양도|자기주식.*취득|자기주식.*처분|자기주식.*소각|소각결정|"
    r"현금.*배당|최대주주.*변경|소송|가처분|거래정지|상장폐지|관리종목|영업정지|"
    r"회생|파산|잠정.*실적|영업.*실적|매출액.*손익|기술이전|임상|품목허가|"
    r"공개매수|경영권|자산양수|자산양도",
    re.I,
)

ROUTINE_RE = re.compile(
    r"임원.?주요주주특정증권등소유상황보고서|주식등의대량보유상황보고서|"
    r"증권발행실적보고서|투자설명서|효력발생안내|일괄신고서|일괄신고추가서류|"
    r"주주명부.*기준일|주주명부폐쇄|주주총회소집결의|주주총회소집공고|"
    r"정기주주총회결과|기업지배구조보고서|사업보고서|반기보고서|분기보고서|"
    r"연결감사보고서|감사보고서|감사보고서제출",
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
    """Reclassify already collected DART rows so resumed V1 runs gain V1.1 filtering."""
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
