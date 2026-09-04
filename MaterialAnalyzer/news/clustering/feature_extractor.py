from __future__ import annotations

import json
import re
import unicodedata

from .models import ArticleFeatures

BRACKET_PREFIX_RE = re.compile(r"^\s*(?:\[[^\]]{1,30}\]|\([^)]+\))\s*")
TOKEN_RE = re.compile(r"[A-Za-z]+\d+[A-Za-z0-9-]*|[가-힣A-Za-z]{2,}|\d+(?:\.\d+)?(?:조원|억원|만원|원|%|GW|MW|kW|척|대|개|건|명|배)?", re.I)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?(?:조원|억원|만원|원|%|GW|MW|kW|척|대|개|건|명|배)?", re.I)

STOPWORDS = {
    "관련", "대한", "통해", "위한", "발표", "보도", "자료", "주요", "정부",
    "이번", "향후", "추진", "진행", "결정", "공시", "회사", "기업", "기자",
}

EVENT_RULES = [
    ("ORDER_CONTRACT", ("단일판매", "공급계약", "수주", "계약체결", "계약 체결", "납품계약")),
    ("CAPITAL_RAISE", ("유상증자", "무상증자", "전환사채", "신주인수권", "교환사채", "제3자배정")),
    ("MNA", ("합병", "분할", "인수", "영업양수", "영업양도", "m&a")),
    ("INVESTMENT", ("시설투자", "신규시설투자", "투자계획", "투자 결정", "증설", "capex")),
    ("EARNINGS", ("잠정실적", "영업실적", "매출액", "손익구조", "실적발표", "실적 발표")),
    ("DIVIDEND", ("현금배당", "현물배당", "배당결정", "배당 결정")),
    ("BUYBACK", ("자기주식", "자사주", "주식소각", "주식 소각")),
    ("APPROVAL", ("품목허가", "허가승인", "허가 승인", "승인", "허가")),
    ("CLINICAL", ("임상시험", "임상 시험", "임상", "시험계획")),
    ("PARTNERSHIP", ("업무협약", "업무 협약", "mou", "파트너십", "협력계약")),
    ("PRODUCT", ("신제품", "출시", "양산", "상용화", "개발완료", "개발 완료")),
    ("POLICY", ("정책", "대책", "로드맵", "지원계획", "지원 계획", "기본계획", "종합계획")),
]

COMPANY_SUFFIXES = ("㈜", "(주)", "주식회사")


def _metadata(row) -> dict:
    raw = row["source_metadata_json"] if "source_metadata_json" in row.keys() else None
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def normalize_company(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    for suffix in COMPANY_SUFFIXES:
        text = text.replace(suffix, "")
    text = re.sub(r"\s+", "", text)
    return text.casefold()


def normalize_title(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip()
    for _ in range(3):
        updated = BRACKET_PREFIX_RE.sub("", text)
        if updated == text:
            break
        text = updated
    text = text.casefold()
    text = re.sub(r"[ㆍ·∙・]", " ", text)
    text = re.sub(r"[^0-9a-z가-힣%]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> tuple[str, ...]:
    result = []
    seen = set()
    for token in TOKEN_RE.findall(text):
        token = token.casefold().strip()
        if len(token) < 2 or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return tuple(result)


def extract_numbers(text: str) -> tuple[str, ...]:
    result = []
    for value in NUMBER_RE.findall(text):
        normalized = value.replace(",", "").casefold()
        if normalized not in result:
            result.append(normalized)
    return tuple(result)


def infer_event_type(text: str) -> str:
    compact = text.casefold()
    for event_type, keywords in EVENT_RULES:
        if any(keyword.casefold() in compact for keyword in keywords):
            return event_type
    return "UNKNOWN"


class FeatureExtractor:
    VERSION = "RULE_FEATURE_V1"

    def extract(self, row) -> ArticleFeatures:
        metadata = _metadata(row)
        title = row["title"] or ""
        body = row["body"] or ""
        summary = row["summary"] or ""
        combined = f"{title} {summary} {body[:3000]}"
        normalized = normalize_title(title)

        companies = []
        for key in ("corp_name", "company_name"):
            company = normalize_company(metadata.get(key))
            if company and company not in companies:
                companies.append(company)
        if row["source_id"] == "KIND":
            company = normalize_company(row["author"])
            if company and company not in companies:
                companies.append(company)

        stock_codes = []
        stock_code = str(metadata.get("stock_code") or "").strip()
        if stock_code and stock_code.isdigit():
            stock_codes.append(stock_code.zfill(6))

        number_text = normalize_title(f"{title} {summary}")
        numbers = extract_numbers(number_text)
        if not numbers and body:
            numbers = extract_numbers(normalize_title(body[:700]))

        return ArticleFeatures(
            article_id=row["article_id"],
            source_id=row["source_id"],
            source_type=row["source_type"] or "",
            source_grade=row["source_grade"] or "",
            article_class=row["article_class"] or "UNKNOWN",
            market_date=row["market_date"],
            normalized_title=normalized,
            tokens=tokenize(normalize_title(combined)),
            companies=tuple(companies),
            stock_codes=tuple(stock_codes),
            numbers=numbers,
            event_type=infer_event_type(combined),
            external_id=row["external_id"],
        )
