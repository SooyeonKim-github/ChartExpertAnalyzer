from __future__ import annotations

import html
import re
import unicodedata


ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
MULTI_SPACE_RE = re.compile(r"[ \t]+")
MULTI_BLANK_RE = re.compile(r"\n{3,}")

BOILERPLATE_PATTERNS = [
    re.compile(r"^copyright\b", re.IGNORECASE),
    re.compile(r"^©\s*\d{4}"),
    re.compile(r"^무단\s*전재"),
    re.compile(r"^무단전재"),
    re.compile(r"^재배포\s*금지"),
    re.compile(r"^all rights reserved", re.IGNORECASE),
]

HASH_TRANSLATION = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‘": "'", "’": "'",
    "–": "-", "—": "-", "−": "-", "…": "...",
})


def _decode(text: str) -> str:
    return html.unescape(text).replace("\r\n", "\n").replace("\r", "\n")


def normalize_display_text(text: str | None) -> str | None:
    if text is None:
        return None
    value = unicodedata.normalize("NFC", _decode(text))
    value = ZERO_WIDTH_RE.sub("", value).replace("\xa0", " ")
    lines = [MULTI_SPACE_RE.sub(" ", line).strip() for line in value.split("\n")]
    value = "\n".join(lines)
    value = MULTI_BLANK_RE.sub("\n\n", value).strip()
    return value or None


def normalize_hash_text(text: str | None) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", _decode(text)).translate(HASH_TRANSLATION)
    value = ZERO_WIDTH_RE.sub("", value).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def normalize_body(text: str | None) -> str | None:
    value = normalize_display_text(text)
    if not value:
        return None
    kept = []
    for line in value.split("\n"):
        stripped = line.strip()
        if stripped and len(stripped) <= 250 and any(pattern.search(stripped) for pattern in BOILERPLATE_PATTERNS):
            continue
        kept.append(stripped)
    cleaned = "\n".join(kept)
    cleaned = MULTI_BLANK_RE.sub("\n\n", cleaned).strip()
    return cleaned or None
