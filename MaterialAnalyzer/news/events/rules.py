from __future__ import annotations

import re


EVENT_RULES = [
    ("TRADING_HALT", ("주권매매거래정지", "매매거래정지", "거래정지")),
    ("SANCTION", ("불성실공시법인지정", "과징금", "제재", "징계", "벌금", "행정처분", "관리종목지정")),
    ("LITIGATION", ("소송등의판결", "소송 등의 판결", "가처분", "소송 제기", "소송제기")),
    ("MARKET_QUERY", ("조회공시요구", "풍문또는보도", "풍문 또는 보도")),
    ("DEBT_GUARANTEE", ("타인에대한채무보증결정", "채무보증결정", "채무 보증")),
    ("IR_EVENT", ("기업설명회", "ir개최", "ir 개최")),
    ("OWNERSHIP_CHANGE", ("임원ㆍ주요주주특정증권등소유상황보고서", "주식등의대량보유상황보고서", "최대주주변경")),
    ("CORPORATE_GOVERNANCE", ("주주총회소집결의", "임시주주총회결과", "정기주주총회결과", "주주명부폐쇄기간", "기준일설정", "대표이사변경", "임원선임", "감사선임")),
    ("ORDER_CONTRACT", ("단일판매", "공급계약", "수주", "계약체결", "납품계약", "도급계약")),
    ("CAPITAL_RAISE", ("유상증자", "무상증자", "전환사채", "신주인수권", "교환사채", "제3자배정", "소액공모공시서류", "일괄신고추가서류")),
    ("MNA", ("합병", "분할", "인수", "영업양수", "영업양도", "m&a", "타법인주식및출자증권취득결정")),
    ("CAPEX", ("신규시설투자", "시설투자", "증설", "공장건설", "설비투자", "capex")),
    ("INVESTMENT", ("투자계획", "투자 결정", "투자협약", "출자결정", "지분투자")),
    ("EARNINGS", ("잠정실적", "영업실적", "매출액", "손익구조", "실적발표", "실적 발표")),
    ("GUIDANCE", ("실적전망", "가이던스", "매출전망", "영업이익전망")),
    ("DIVIDEND", ("현금배당", "현물배당", "배당결정", "배당 결정")),
    ("BUYBACK", ("자기주식취득", "자사주취득", "자기주식소각", "주식소각", "자사주 소각")),
    ("APPROVAL", ("품목허가", "허가승인", "허가 승인", "식약처 승인", "승인 획득", "허가 획득")),
    ("CLINICAL", ("임상시험", "임상 시험", "임상 1상", "임상 2상", "임상 3상", "시험계획")),
    ("PATENT", ("특허취득", "특허 등록", "특허출원", "특허 출원")),
    ("PARTNERSHIP", ("업무협약", "업무 협약", "mou", "파트너십", "전략적 협력", "협력계약")),
    ("PRODUCT", ("신제품", "출시", "양산", "상용화", "개발완료", "개발 완료")),
    ("PRICE_INCREASE", ("가격 인상", "판매가격 인상", "가격인상")),
    ("SHORTAGE", ("공급 부족", "품귀", "쇼티지", "수급 부족")),
    ("SUBSIDY", ("보조금", "지원금", "세액공제", "인센티브 지원")),
    ("DEFENSE", ("방위사업", "방산", "무기체계", "전차", "자주포", "미사일")),
    ("NUCLEAR", ("원전", "원자력", "소형모듈원전", "smr")),
    ("AI_DATACENTER", ("ai 데이터센터", "데이터센터", "gpu 센터", "ai 인프라")),
    ("AI", ("인공지능", "ai 파운데이션 모델", "독자 ai", "모두의 ai", "agi")),
    ("RND", ("r&d", "연구개발", "연구개발 사업", "연구개발특구")),
    ("REGULATION", ("규제 완화", "규제개선", "기준 명확화", "제도 개선", "제도개선")),
    ("RECALL", ("회수 조치", "판매중단", "판매 중단", "리콜")),
    ("SECONDARY_BATTERY", ("이차전지", "2차전지", "배터리", "양극재", "음극재")),
    ("SEMICONDUCTOR", ("반도체", "hbm", "파운드리", "dram", "낸드")),
    ("SHIPBUILDING", ("조선", "lng선", "lng 운반선", "컨테이너선", "탱커")),
    ("BIO", ("바이오", "신약", "의약품", "의료기기")),
    ("SUPPLY", ("공급확대", "공급 확대", "공급개시", "공급 개시")),
    ("GOV_POLICY", ("정책", "대책", "로드맵", "지원계획", "지원 계획", "기본계획", "종합계획", "육성계획", "보급 계획", "보급계획")),
]

STAGE_RULES = [
    ("COMPLETED", ("완료", "준공", "종료", "최종 완료")),
    ("STARTED", ("가동", "착공", "개시", "양산 시작", "판매 시작", "출시")),
    ("APPROVED", ("승인", "허가", "인가")),
    ("CONFIRMED", ("체결", "수주", "결정", "확정", "선정", "지정", "취득", "계약")),
    ("PLANNED", ("계획", "예정", "목표", "추진", "검토", "로드맵")),
]

NEGATIVE_KEYWORDS = (
    "거래정지", "불성실공시", "과징금", "제재", "리콜", "임상중단", "임상 중단",
    "횡령", "배임", "적자전환", "영업손실", "상장폐지", "감사의견 거절", "계약해지",
)
POSITIVE_KEYWORDS = (
    "수주", "공급계약", "계약체결", "승인", "허가", "신제품", "출시", "양산",
    "증설", "주식소각", "자사주 소각", "특허취득", "실적개선", "흑자전환",
)

SPACE_RE = re.compile(r"\s+")


def normalize_rule_text(value: str | None) -> str:
    text = (value or "").casefold().replace("ㆍ", " ").replace("·", " ")
    return SPACE_RE.sub(" ", text).strip()


def infer_event_type(text: str) -> str:
    compact = normalize_rule_text(text)
    for event_type, keywords in EVENT_RULES:
        if any(normalize_rule_text(keyword) in compact for keyword in keywords):
            return event_type
    return "UNKNOWN"


def infer_stage(text: str, source_ids: set[str]) -> str:
    compact = normalize_rule_text(text)
    for stage, keywords in STAGE_RULES:
        if any(normalize_rule_text(keyword) in compact for keyword in keywords):
            return stage
    if source_ids & {"DART", "KIND"}:
        return "CONFIRMED"
    if source_ids:
        return "ANNOUNCED"
    return "UNKNOWN"


def infer_polarity(text: str, event_type: str) -> str:
    compact = normalize_rule_text(text)
    if any(normalize_rule_text(keyword) in compact for keyword in NEGATIVE_KEYWORDS):
        return "NEGATIVE"
    if event_type in {"TRADING_HALT", "SANCTION"}:
        return "NEGATIVE"
    if any(normalize_rule_text(keyword) in compact for keyword in POSITIVE_KEYWORDS):
        return "POSITIVE"
    return "NEUTRAL"
