from __future__ import annotations

import re

from ..clustering.feature_extractor import normalize_title


# High-precision litigation subjects. These are intentionally concrete: two lawsuits filed
# by the same company on the same day must not become one family just because both contain
# generic words such as '가처분' or '항고'.
SUBJECT_PATTERNS = (
    ("전환사채발행금지", ("전환사채발행금지", "전환사채 발행 금지", "전환사채 발행금지")),
    ("신주발행금지", ("신주발행금지", "신주 발행 금지", "신주 발행금지")),
    ("신주발행무효", ("신주발행무효", "신주 발행 무효")),
    ("의결권행사금지", ("의결권행사금지", "의결권 행사 금지")),
    ("주주총회결의효력정지", ("주주총회결의효력정지", "주주총회 결의 효력 정지")),
    ("이사직무집행정지", ("이사직무집행정지", "이사 직무 집행 정지")),
    ("회계장부열람등사", ("회계장부열람", "회계장부 열람", "열람등사")),
    ("주식처분금지", ("주식처분금지", "주식 처분 금지")),
)

PROCEDURE_PATTERNS = (
    ("REAPPEAL", ("재항고",)),
    ("APPEAL", ("항고",)),
    ("FINAL", ("확정",)),
    ("JUDGMENT", ("판결",)),
    ("ACCEPTED", ("인용",)),
    ("DISMISSED", ("기각", "각하")),
    ("WITHDRAWN", ("취하",)),
    ("DECISION", ("결정",)),
    ("FILED", ("신청", "제기")),
)

PROCEDURE_RANK = {
    "": 0,
    "FILED": 1,
    "DECISION": 2,
    "ACCEPTED": 3,
    "DISMISSED": 3,
    "APPEAL": 4,
    "REAPPEAL": 5,
    "JUDGMENT": 6,
    "FINAL": 7,
    "WITHDRAWN": 7,
}

SPACE_RE = re.compile(r"\s+")


def _compact(value: str | None) -> str:
    return SPACE_RE.sub(" ", normalize_title(value or "")).strip()


def litigation_subject(title: str | None) -> str:
    compact = _compact(title)
    compact_no_space = compact.replace(" ", "")
    for subject, patterns in SUBJECT_PATTERNS:
        for pattern in patterns:
            normalized = _compact(pattern)
            if normalized in compact or normalized.replace(" ", "") in compact_no_space:
                return subject
    return ""


def litigation_procedure(title: str | None) -> str:
    compact = _compact(title)
    for procedure, patterns in PROCEDURE_PATTERNS:
        if any(_compact(pattern) in compact for pattern in patterns):
            return procedure
    return ""


def same_litigation_subject(left_title: str | None, right_title: str | None) -> bool:
    left = litigation_subject(left_title)
    right = litigation_subject(right_title)
    return bool(left and right and left == right)


def litigation_subject_conflict(left_title: str | None, right_title: str | None) -> bool:
    left = litigation_subject(left_title)
    right = litigation_subject(right_title)
    return bool(left and right and left != right)


def litigation_procedure_progressed(current_title: str | None, parent_title: str | None) -> bool:
    if not same_litigation_subject(current_title, parent_title):
        return False
    current = litigation_procedure(current_title)
    parent = litigation_procedure(parent_title)
    if not current or not parent or current == parent:
        return False
    return PROCEDURE_RANK.get(current, 0) > PROCEDURE_RANK.get(parent, 0)
