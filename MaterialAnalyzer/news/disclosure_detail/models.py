from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DisclosureDetailInput:
    event_id: str
    rcept_no: str
    event_type: str
    event_title: str
    companies: tuple[str, ...] = field(default_factory=tuple)
    stock_codes: tuple[str, ...] = field(default_factory=tuple)
    event_updated_at: str | None = None


@dataclass(frozen=True)
class DisclosureDetailRecord:
    event_id: str
    rcept_no: str
    detail_type: str
    detail_event_key: str
    source_document_name: str
    contract_amount: float | None
    recent_sales: float | None
    sales_ratio: float | None
    counterparty: str
    contract_subject: str
    contract_start_date: str | None
    contract_end_date: str | None
    correction_before: dict[str, Any]
    correction_after: dict[str, Any]
    raw_detail: dict[str, Any]
    parse_status: str
    parse_confidence: float
    error_message: str
    parser_version: str
    event_updated_at: str | None


@dataclass
class DisclosureDetailRunResult:
    processed: int = 0
    inserted: int = 0
    updated: int = 0
    success: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
