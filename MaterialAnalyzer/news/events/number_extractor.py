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
    # Limit duration to 1-3 digits and omit bare '일' to avoid YYYY년/MM월/DD일 dates.
    ("DURATION", re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*(개월|년|주)\b", re.I)),
    ("CLINICAL_PHASE", re.compile(r"(?<!\d)([123])\s*(상)\b")),
]


def _normalize_value(number: str, unit: str) -> str:
    number = number.replace(",", "").strip()
    unit = re.sub(r"\s+", "", unit).strip()
    return f"{number}{unit}"


def _iter_values(pattern: re.Pattern, text: str):
    for match in pattern.finditer(text):
        # PATTERNS are required to provide exactly two capture groups.
        # Keep this explicit so malformed future patterns fail here during tests.
        if pattern.groups != 2:
            raise ValueError(f"meaningful-number pattern must have 2 groups, got {pattern.groups}: {pattern.pattern}")
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
