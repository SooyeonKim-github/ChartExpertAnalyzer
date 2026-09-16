from __future__ import annotations

import json

from .contract_parser import ContractDisclosureParser, build_detail_event_key
from .dart_document_client import DartDocumentClient
from .dart_document_parser import DartDocumentParser
from .models import DisclosureDetailInput, DisclosureDetailRecord, DisclosureDetailRunResult


def _json_tuple(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(x) for x in value if str(x))
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ()
    return tuple(str(x) for x in parsed if str(x)) if isinstance(parsed, list) else ()


def input_from_row(row) -> DisclosureDetailInput:
    return DisclosureDetailInput(
        event_id=row["event_id"],
        rcept_no=(row["rcept_no"] or "").strip(),
        event_type=row["event_type"] or "UNKNOWN",
        event_title=row["event_title"] or "",
        companies=_json_tuple(row["companies_json"]),
        stock_codes=_json_tuple(row["stock_codes_json"]),
        event_updated_at=row["updated_at"],
    )


class DisclosureDetailAnalyzer:
    VERSION = ContractDisclosureParser.VERSION
    TARGET_EVENT_TYPES = {"ORDER_CONTRACT"}

    def __init__(
        self,
        repository,
        *,
        client: DartDocumentClient | None = None,
        document_parser: DartDocumentParser | None = None,
        contract_parser: ContractDisclosureParser | None = None,
    ):
        self.repository = repository
        self.client = client or DartDocumentClient()
        self.document_parser = document_parser or DartDocumentParser()
        self.contract_parser = contract_parser or ContractDisclosureParser()

    def _record_error(self, event: DisclosureDetailInput, message: str) -> DisclosureDetailRecord:
        return DisclosureDetailRecord(
            event_id=event.event_id,
            rcept_no=event.rcept_no,
            detail_type=event.event_type,
            detail_event_key="",
            source_document_name="",
            contract_amount=None,
            recent_sales=None,
            sales_ratio=None,
            counterparty="",
            contract_subject="",
            contract_start_date=None,
            contract_end_date=None,
            correction_before={},
            correction_after={},
            raw_detail={},
            parse_status="FAILED",
            parse_confidence=0.0,
            error_message=message[:1000],
            parser_version=self.VERSION,
            event_updated_at=event.event_updated_at,
        )

    def enrich(self, event: DisclosureDetailInput) -> DisclosureDetailRecord:
        archive = self.client.download(event.rcept_no)
        part = self.document_parser.select_contract_document(archive)
        rows = self.document_parser.table_rows(part.text)
        parsed = self.contract_parser.parse(rows)
        values = parsed.values

        counterparty = str(values.get("counterparty") or "")
        contract_subject = str(values.get("contract_subject") or "")
        detail_key = build_detail_event_key(
            stock_codes=event.stock_codes,
            companies=event.companies,
            counterparty=counterparty,
            contract_subject=contract_subject,
        )
        raw_detail = dict(parsed.raw_detail)
        raw_detail["selected_document"] = part.name
        raw_detail["document_score"] = round(part.score, 3)
        raw_detail["table_row_count"] = len(rows)

        return DisclosureDetailRecord(
            event_id=event.event_id,
            rcept_no=event.rcept_no,
            detail_type=event.event_type,
            detail_event_key=detail_key,
            source_document_name=part.name,
            contract_amount=values.get("contract_amount"),
            recent_sales=values.get("recent_sales"),
            sales_ratio=values.get("sales_ratio"),
            counterparty=counterparty,
            contract_subject=contract_subject,
            contract_start_date=values.get("contract_start_date"),
            contract_end_date=values.get("contract_end_date"),
            correction_before=parsed.correction_before,
            correction_after=parsed.correction_after,
            raw_detail=raw_detail,
            parse_status=parsed.status,
            parse_confidence=parsed.confidence,
            error_message="",
            parser_version=self.VERSION,
            event_updated_at=event.event_updated_at,
        )

    def run(self, *, rebuild: bool = False, limit: int | None = None) -> DisclosureDetailRunResult:
        if rebuild:
            self.repository.clear_all()
        self.repository.prune_orphans()

        rows = self.repository.get_pending_events(parser_version=self.VERSION, limit=limit)
        result = DisclosureDetailRunResult()
        if rows and not self.client.available:
            result.skipped = len(rows)
            result.total = self.repository.count()
            return result

        for row in rows:
            event = input_from_row(row)
            result.processed += 1
            try:
                record = self.enrich(event)
            except Exception as exc:
                record = self._record_error(event, f"{type(exc).__name__}: {exc}")

            action = self.repository.upsert(record)
            if action == "INSERTED":
                result.inserted += 1
            else:
                result.updated += 1

            if record.parse_status == "SUCCESS":
                result.success += 1
            elif record.parse_status in {"PARTIAL", "NO_DETAIL"}:
                result.partial += 1
            else:
                result.failed += 1

        result.total = self.repository.count()
        return result
