from __future__ import annotations

import hashlib
import re
from typing import Iterable

from ..clustering.feature_extractor import normalize_company, normalize_title


REVISION_PREFIX_RE = re.compile(r"^(?:기재정정|첨부정정|본문정정|정정)\s*", re.I)

# These disclosure titles do not identify one business event by themselves. For such
# rows we deliberately add market_date to the canonical key to avoid merging unrelated
# contracts/corporate actions from the same company. A later detail/delta layer can
# replace this conservative daily scope with counterparty/subject based identity.
GENERIC_DISCLOSURE_ANCHORS = {
    "단일판매 공급계약체결",
    "단일판매 공급계약 체결",
    "유상증자결정",
    "무상증자결정",
    "현금 현물배당결정",
    "현금배당결정",
    "자기주식취득결정",
    "자기주식처분결정",
    "주식소각결정",
    "자기주식소각결정",
    "최대주주변경",
    "대표이사변경",
    "합병결정",
    "회사분할결정",
    "타법인주식및출자증권취득결정",
    "타법인주식및출자증권처분결정",
    "신규시설투자등",
    "신규시설투자",
    "전환사채권발행결정",
    "신주인수권부사채권발행결정",
    "교환사채권발행결정",
    "자기전환사채매도결정",
    "감자결정",
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _row_value(row, key: str, default=""):
    try:
        if hasattr(row, "keys") and key not in row.keys():
            return default
        value = row[key]
    except (KeyError, TypeError, IndexError):
        return default
    return default if value is None else value


def _clean_anchor(value: str | None) -> str:
    anchor = normalize_title(value or "")
    anchor = REVISION_PREFIX_RE.sub("", anchor).strip()
    return anchor


def _subject_key(companies: Iterable[str], stock_codes: Iterable[str]) -> str:
    tickers = sorted({str(code).strip().zfill(6) for code in stock_codes if str(code).strip()})
    if tickers:
        return "ticker:" + ",".join(tickers)

    normalized_companies = sorted({normalize_company(name) for name in companies if normalize_company(name)})
    if normalized_companies:
        return "company:" + ",".join(normalized_companies)

    return "market"


def build_document_signature(representative) -> str:
    """Build a stable identity for the representative source document.

    Prefer the source-native immutable id (DART rcept_no, KIND id, etc.). When a
    collector does not expose one, article_id/canonical URL are used as fallbacks.
    This signature intentionally says "same document", not "same business event".
    """

    source_id = str(_row_value(representative, "source_id", "") or "").strip().upper()
    external_id = str(_row_value(representative, "external_id", "") or "").strip()
    article_id = str(_row_value(representative, "article_id", "") or "").strip()
    canonical_url = str(_row_value(representative, "canonical_url", "") or "").strip()
    url = str(_row_value(representative, "url", "") or "").strip()
    published_at = str(_row_value(representative, "published_at", "") or "").strip()
    title = _clean_anchor(str(_row_value(representative, "title", "") or ""))

    if external_id:
        identity = f"external:{external_id}"
    elif article_id:
        identity = f"article:{article_id}"
    elif canonical_url or url:
        identity = f"url:{canonical_url or url}"
    else:
        identity = f"fallback:{published_at}|{title}"

    return f"DOC_{_digest(f'{source_id}|{identity}')}"


def build_canonical_event_key(
    *,
    event_type: str,
    event_title: str,
    event_summary: str,
    companies: Iterable[str] = (),
    stock_codes: Iterable[str] = (),
    market_date: str | None = None,
    source_id: str = "",
) -> str:
    """Build a conservative business-event identity.

    Revision labels are removed so e.g. ``[기재정정] ... (4회차)`` and the original
    title produce the same key. DART/KIND use the normalized disclosure title rather
    than summary/body because those contents can change in the correction itself.

    Generic DART/KIND disclosure names are daily-scoped because the current collector
    does not yet parse counterparty/contract subject; merging those across dates would
    create worse false positives. The disclosure-detail/delta analyzer can later
    promote them to a stronger cross-date key.
    """

    event_type_norm = str(event_type or "UNKNOWN").strip().upper() or "UNKNOWN"
    title_anchor = _clean_anchor(event_title)
    summary_anchor = _clean_anchor(event_summary)
    source_norm = str(source_id or "").strip().upper()

    if source_norm in {"DART", "KIND"}:
        anchor = title_anchor[:240]
    elif summary_anchor and summary_anchor != title_anchor and len(summary_anchor) >= 12:
        anchor = summary_anchor[:240]
    else:
        anchor = title_anchor[:240]

    subject = _subject_key(companies, stock_codes)
    parts = [subject, event_type_norm, anchor or "unknown"]
    if source_norm in {"DART", "KIND"} and anchor in GENERIC_DISCLOSURE_ANCHORS:
        parts.append(f"day:{market_date or 'unknown'}")

    return f"CEK_{_digest('|'.join(parts))}"
