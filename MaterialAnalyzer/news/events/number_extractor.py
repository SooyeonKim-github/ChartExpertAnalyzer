from __future__ import annotations

import re


# Numbers without business meaning (dates, phone numbers, article ids) are intentionally ignored.
# A value is kept only when a recognizable unit/context is present.
# Every regex intentionally exposes exactly two capture groups: numeric value + unit.
PATTERNS = [
    ("MONEY", re.compile(r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(억\s*달러|만\s*달러|조\s*원|억\s*원|조원|억원|만원|달러|원)", re.I)),
    ("PERCENT", re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*(퍼센트|%)", re.I)),
    ("CAPACITY", re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*(GWh|MWh|kWh|GW|MW|kW|PB|TB)", re.I)),
    ("QUANTITY", re.compile(r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(개사|호기|척|대|개|건|명|기|곳|종|회)", re.I)),
    # Korean suffixes such as '3년간' do not form a Python \b boundary after '년'.
    # Use a digit guard instead so meaningful durations embedded in Korean text are retained.
    ("DURATION", re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*(개월|년|주)(?!\d)", re.I)),
    # Python's Unicode \b does not match '2상에서' because both '상' and '에' are word chars.
    # A digit guard correctly accepts '2상', '2상에서', and '2상시험'.
    ("CLINICAL_PHASE", re.compile(r"(?<!\d)([123])\s*(상)(?!\d)")),
]


def _normalize_value(number: str, unit: str) -> str:
    number = number.replace(",", "").strip()
    unit = re.sub(r"\s+", "", unit).strip()
    return f"{number}{unit}"


def _iter_values(pattern: re.Pattern, text: str):
    # Fail immediately even when a malformed future regex happens to match nothing.
    if pattern.groups != 2:
        raise ValueError(
            f"meaningful-number pattern must have 2 groups, got {pattern.groups}: {pattern.pattern}"
        )
    for match in pattern.finditer(text):
        yield _normalize_value(match.group(1), match.group(2))


def extract_meaningful_numbers(*texts: str | None) -> tuple[str, ...]:
    values: list[str] = []
    seen = set()
    text = " ".join(value or "" for value in texts)
    for _, pattern in PATTERNS:
        for value in _iter_values(pattern, text):
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                values.append(value)
    return tuple(values)


def classify_meaningful_numbers(*texts: str | None) -> dict[str, tuple[str, ...]]:
    text = " ".join(value or "" for value in texts)
    result: dict[str, tuple[str, ...]] = {}
    for category, pattern in PATTERNS:
        values: list[str] = []
        seen = set()
        for value in _iter_values(pattern, text):
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                values.append(value)
        if values:
            result[category] = tuple(values)
    return result
