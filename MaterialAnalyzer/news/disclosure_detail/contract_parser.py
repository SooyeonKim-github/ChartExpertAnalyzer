from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from ..clustering.feature_extractor import normalize_company, normalize_title


NON_LABEL_RE = re.compile(r"[\sㆍ·∙・()\[\]{}:;,_/\\.-]+")
NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")

FIELD_ALIASES = {
    "contract_amount": (
        "계약금액", "계약 금액", "계약금액(원)", "계약금액 원", "판매공급계약금액"
    ),
    "recent_sales": (
        "최근매출액", "최근 매출액", "최근매출액(원)", "최근매출액 원"
    ),
    "sales_ratio": (
        "매출액대비", "매출액 대비", "최근매출액대비", "최근 매출액 대비", "매출액대비(%)"
    ),
    "counterparty": (
        "계약상대방", "계약 상대방", "계약상대", "계약 상대"
    ),
    "contract_subject": (
        "계약내용", "계약 내용", "판매공급계약내용", "판매 공급계약 내용", "계약명", "공급내용"
    ),
    "contract_start_date": (
        "계약기간시작일", "계약기간 시작일", "계약 시작일", "시작일"
    ),
    "contract_end_date": (
        "계약기간종료일", "계약기간 종료일", "계약 종료일", "종료일"
    ),
}


def normalize_label(value: str | None) -> str:
    text = str(value or "").casefold().strip()
    return NON_LABEL_RE.sub("", text)


NORMALIZED_ALIASES = {
    field: tuple(normalize_label(alias) for alias in aliases)
    for field, aliases in FIELD_ALIASES.items()
}


def match_field(label: str | None) -> str | None:
    key = normalize_label(label)
    if not key:
        return None
    candidates: list[tuple[int, str]] = []
    for field, aliases in NORMALIZED_ALIASES.items():
        for alias in aliases:
            if key == alias or (len(alias) >= 4 and alias in key):
                candidates.append((len(alias), field))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _number(value: str | None) -> float | None:
    match = NUMBER_RE.search(str(value or "").replace("\xa0", " "))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_money(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    number = _number(text)
    if number is None:
        return None
    compact = text.casefold().replace(" ", "")
    if "조원" in compact:
        return number * 1_000_000_000_000
    if "억원" in compact:
        return number * 100_000_000
    if "만원" in compact:
        return number * 10_000
    # DART contract tables usually label this field '(원)', so a unit-less numeric cell
    # is interpreted as KRW rather than as an abstract quantity.
    return number


def parse_ratio(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return _number(str(value))


def parse_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text in {"-", "해당없음", "해당 없음"}:
        return None
    compact = re.sub(r"\s+", "", text)
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y%m%d", "%Y년%m월%d일"):
        try:
            return datetime.strptime(compact, fmt).date().isoformat()
        except ValueError:
            continue
    match = re.search(r"(20\d{2})\D+(\d{1,2})\D+(\d{1,2})", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date().isoformat()
        except ValueError:
            pass
    return None


def convert_field(field: str, value: Any) -> Any:
    if field in {"contract_amount", "recent_sales"}:
        return parse_money(value)
    if field == "sales_ratio":
        return parse_ratio(value)
    if field in {"contract_start_date", "contract_end_date"}:
        return parse_date(value)
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _next_value(cells: list[str], index: int) -> str:
    for value in cells[index + 1 :]:
        if value and match_field(value) is None:
            return value
    return ""


def extract_fields(rows: Iterable[list[str]]) -> tuple[dict[str, Any], dict[str, str]]:
    parsed: dict[str, Any] = {}
    raw: dict[str, str] = {}
    for cells in rows:
        for index, cell in enumerate(cells[:-1]):
            field = match_field(cell)
            if not field or field in parsed:
                continue
            value = _next_value(cells, index)
            if not value:
                continue
            converted = convert_field(field, value)
            if converted is None or converted == "":
                continue
            parsed[field] = converted
            raw[field] = value
    return parsed, raw


def _header_indices(cells: list[str]) -> tuple[int | None, int | None]:
    before_idx = after_idx = None
    for idx, value in enumerate(cells):
        key = normalize_label(value)
        if "정정전" in key or "변경전" in key:
            before_idx = idx
        if "정정후" in key or "변경후" in key:
            after_idx = idx
    return before_idx, after_idx


def extract_correction(rows: list[list[str]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    raw: dict[str, Any] = {}

    for header_index, header in enumerate(rows):
        before_idx, after_idx = _header_indices(header)
        if before_idx is None or after_idx is None:
            continue
        for cells in rows[header_index + 1 :]:
            if max(before_idx, after_idx) >= len(cells):
                continue
            field = None
            label = ""
            for candidate in cells[: max(1, min(before_idx, after_idx)) + 1]:
                field = match_field(candidate)
                if field:
                    label = candidate
                    break
            if not field:
                # A new unrelated table/header usually means the correction section ended.
                if _header_indices(cells) != (None, None):
                    break
                continue
            before_raw = cells[before_idx]
            after_raw = cells[after_idx]
            before_value = convert_field(field, before_raw)
            after_value = convert_field(field, after_raw)
            if before_value is not None and before_value != "":
                before[field] = before_value
            if after_value is not None and after_value != "":
                after[field] = after_value
            raw[field] = {"label": label, "before": before_raw, "after": after_raw}
        if before or after:
            break

    return before, after, raw


def build_detail_event_key(
    *,
    stock_codes: Iterable[str] = (),
    companies: Iterable[str] = (),
    counterparty: str = "",
    contract_subject: str = "",
) -> str:
    tickers = sorted({str(code).strip().zfill(6) for code in stock_codes if str(code).strip()})
    if tickers:
        subject = "ticker:" + ",".join(tickers)
    else:
        names = sorted({normalize_company(name) for name in companies if normalize_company(name)})
        subject = "company:" + ",".join(names) if names else "market"

    counterparty_key = normalize_company(counterparty)
    contract_key = normalize_title(contract_subject)[:160]
    if not (counterparty_key or contract_key):
        return ""
    raw = f"{subject}|ORDER_CONTRACT|{counterparty_key}|{contract_key}"
    return "DEK_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class ContractParseResult:
    values: dict[str, Any]
    correction_before: dict[str, Any]
    correction_after: dict[str, Any]
    raw_detail: dict[str, Any]
    confidence: float
    status: str


class ContractDisclosureParser:
    VERSION = "ORDER_CONTRACT_DETAIL_V1_1"

    def parse(self, rows: list[list[str]]) -> ContractParseResult:
        values, raw_fields = extract_fields(rows)
        before, after, correction_raw = extract_correction(rows)

        # In a correction filing, the 'after' side is the current truth. Prefer it when
        # the main contract table was not present or did not expose the corrected field.
        for field, value in after.items():
            values[field] = value

        core = ("contract_amount", "counterparty", "contract_subject")
        found_core = sum(1 for field in core if values.get(field) not in (None, ""))
        optional = ("recent_sales", "sales_ratio", "contract_start_date", "contract_end_date")
        found_optional = sum(1 for field in optional if values.get(field) not in (None, ""))

        confidence = min(100.0, 35.0 + found_core * 15.0 + found_optional * 5.0 + (10.0 if before or after else 0.0))
        if found_core >= 2:
            status = "SUCCESS"
        elif found_core or found_optional or before or after:
            status = "PARTIAL"
        else:
            status = "NO_DETAIL"

        return ContractParseResult(
            values=values,
            correction_before=before,
            correction_after=after,
            raw_detail={"fields": raw_fields, "correction": correction_raw},
            confidence=confidence,
            status=status,
        )
