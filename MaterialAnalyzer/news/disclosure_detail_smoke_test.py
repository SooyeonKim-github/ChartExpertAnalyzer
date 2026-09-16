from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from .disclosure_delta.detector import DisclosureDeltaDetector
from .disclosure_delta.models import DisclosureDeltaInput
from .disclosure_detail.contract_parser import ContractDisclosureParser, build_detail_event_key
from .disclosure_detail.dart_document_parser import DartDocumentParser


HTML = """
<html><body>
<table>
<tr><td>판매ㆍ공급계약 내용</td><td>전술정보통신체계 공급</td></tr>
<tr><td>계약금액(원)</td><td>30,000,000,000</td></tr>
<tr><td>최근매출액(원)</td><td>490,000,000,000</td></tr>
<tr><td>매출액 대비(%)</td><td>6.12</td></tr>
<tr><td>계약상대방</td><td>방위사업청</td></tr>
<tr><td>계약기간 시작일</td><td>2026-09-15</td></tr>
<tr><td>계약기간 종료일</td><td>2028-12-31</td></tr>
</table>
<table>
<tr><th>정정항목</th><th>정정전</th><th>정정후</th></tr>
<tr><td>계약금액(원)</td><td>50,000,000,000</td><td>30,000,000,000</td></tr>
<tr><td>매출액 대비(%)</td><td>10.20</td><td>6.12</td></tr>
</table>
</body></html>
"""

NOISE = "<html><body><table><tr><td>첨부</td><td>일반 문서</td></tr></table></body></html>"


def _zip() -> bytes:
    out = BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as zf:
        zf.writestr("noise.xml", NOISE.encode("utf-8"))
        zf.writestr("contract.xml", HTML.encode("utf-8"))
    return out.getvalue()


def main():
    document_parser = DartDocumentParser()
    part = document_parser.select_contract_document(_zip())
    assert part.name == "contract.xml"
    rows = document_parser.table_rows(part.text)
    assert rows

    parsed = ContractDisclosureParser().parse(rows)
    assert parsed.status == "SUCCESS"
    assert parsed.values["contract_amount"] == 30_000_000_000
    assert parsed.values["recent_sales"] == 490_000_000_000
    assert parsed.values["sales_ratio"] == 6.12
    assert parsed.values["counterparty"] == "방위사업청"
    assert parsed.values["contract_subject"] == "전술정보통신체계 공급"
    assert parsed.values["contract_start_date"] == "2026-09-15"
    assert parsed.values["contract_end_date"] == "2028-12-31"
    assert parsed.correction_before["contract_amount"] == 50_000_000_000
    assert parsed.correction_after["contract_amount"] == 30_000_000_000
    assert parsed.correction_before["sales_ratio"] == 10.2
    assert parsed.correction_after["sales_ratio"] == 6.12

    first_key = build_detail_event_key(
        stock_codes=("272210",),
        counterparty="방위사업청",
        contract_subject="전술정보통신체계 공급",
    )
    second_key = build_detail_event_key(
        stock_codes=("272210",),
        counterparty="방위 사업청",
        contract_subject="전술정보통신체계  공급",
    )
    assert first_key
    assert first_key == second_key

    correction = DisclosureDeltaInput(
        event_id="EV_CORRECTION",
        canonical_event_key="CEK_DAILY",
        event_type="ORDER_CONTRACT",
        event_stage="CONFIRMED",
        event_title="[기재정정]단일판매ㆍ공급계약체결",
        event_summary="",
        positive_negative="POSITIVE",
        companies=("테스트기업",),
        stock_codes=("272210",),
        numbers=(),
        original_source_id="DART",
        detail_event_key=first_key,
        detail_contract_amount=30_000_000_000,
        detail_sales_ratio=6.12,
        detail_counterparty="방위사업청",
        detail_contract_subject="전술정보통신체계 공급",
        correction_before={"contract_amount": 50_000_000_000.0, "sales_ratio": 10.2},
        correction_after={"contract_amount": 30_000_000_000.0, "sales_ratio": 6.12},
        detail_parse_status="SUCCESS",
        detail_updated_at="2026-09-16 11:00:00",
    )
    delta = DisclosureDeltaDetector().detect(correction, None)
    assert delta.delta_type == "CONTRACT_DECREASE"
    assert delta.delta_direction == "DECREASE"
    assert delta.effective_sentiment == "NEGATIVE"
    assert delta.numeric_kind == "money"
    assert delta.numeric_change_pct == -40.0

    print("[OK] DisclosureDetailEnricher V1.1 smoke test")
    print("     OpenDART ZIP contract document selection -> OK")
    print("     contract amount/sales ratio/counterparty/subject/dates -> OK")
    print("     correction before/after table -> OK")
    print("     detail_event_key normalization -> OK")
    print("     correction table 500eok -> 300eok = CONTRACT_DECREASE / NEGATIVE -> OK")


if __name__ == "__main__":
    main()
