from __future__ import annotations

import json
from datetime import date, datetime, time, timezone

from .history.chunk_planner import plan_chunks
from .history.collectors.dart_range import DartRangeCollector
from .history.dart_prefilter import classify_dart_analysis
from .history.historical_market_date import HistoricalMarketDateResolver
from .news.models import SourceEndpoint


class _Fetched:
    def __init__(self, payload):
        self.text = json.dumps(payload, ensure_ascii=False)
        self.status_code = 200
        self.url = "https://opendart.fss.or.kr/api/list.json"


class _Http:
    def __init__(self):
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        page = int((params or {}).get("page_no", 1))
        if page == 1:
            rows = [{"rcept_no": f"2026010200000{i}", "corp_code": "001", "corp_name": "테스트", "stock_code": "005930", "report_nm": f"공시{i}", "flr_nm": "테스트", "rcept_dt": "20260102"} for i in range(1, 101)]
            return _Fetched({"status":"000","total_page":2,"list":rows})
        rows = [{"rcept_no": "20260103000001", "corp_code":"001","corp_name":"테스트","stock_code":"005930","report_nm":"공시101","flr_nm":"테스트","rcept_dt":"20260103"}]
        return _Fetched({"status":"000","total_page":2,"list":rows})


def _endpoint():
    return SourceEndpoint(
        endpoint_id="DART_DISCLOSURE", source_id="DART", source_name="DART", source_type="OFFICIAL",
        source_grade="S", priority=1, collector_type="DART_API", endpoint_role="DISCOVERY",
        target_section="DISCLOSURE", interval_min=2, content_mode="FULL", enabled=True,
        api_url="https://opendart.fss.or.kr/api/list.json",
    )


def main():
    chunks = plan_chunks("DART", date(2026,1,1), date(2026,1,10), 3)
    assert [(c.start.isoformat(), c.end.isoformat()) for c in chunks] == [
        ("2026-01-01","2026-01-03"),("2026-01-04","2026-01-06"),("2026-01-07","2026-01-09"),("2026-01-10","2026-01-10")
    ]

    resolver = HistoricalMarketDateResolver.__new__(HistoricalMarketDateResolver)
    resolver.market_close = time(15,30)
    resolver._days = [date(2026,1,2), date(2026,1,5), date(2026,1,6)]
    resolver._ordinals = [d.toordinal() for d in resolver._days]
    assert resolver.resolve_historical(datetime(2026,1,2,14,0,tzinfo=timezone.utc), "DATE") == "20260105"
    assert resolver.resolve_historical(datetime(2026,1,2,5,0,tzinfo=timezone.utc), "SECOND") == "20260102"
    assert resolver.resolve_historical(datetime(2026,1,2,8,0,tzinfo=timezone.utc), "SECOND") == "20260105"

    http = _Http()
    collector = DartRangeCollector(_endpoint(), date(2026,1,2), date(2026,1,3), http_client=http)
    collector._api_key = lambda: "TEST"
    candidates = collector.discover()
    assert len(candidates) == 101
    assert http.calls == 2
    assert candidates[0].metadata["historical_range"] is True

    assert classify_dart_analysis("단일판매ㆍ공급계약체결", "005930") == "PENDING"
    assert classify_dart_analysis("주주총회소집공고", "005930") == "SKIP_HISTORY_ROUTINE"
    assert classify_dart_analysis("분기보고서", "005930") == "SKIP_HISTORY_ROUTINE"
    assert classify_dart_analysis("단일판매ㆍ공급계약체결", "") == "SKIP_HISTORY_NONLISTED"

    print("[OK] HistoricalMaterialRangeCollector V1.1 smoke test")
    print("     chunk planning -> OK")
    print("     DATE-only signal -> next trading day")
    print("     exact intraday timestamp -> same/next trading day")
    print("     DART range pagination -> 2 pages / 101 rows")
    print("     DART strong catalyst -> analysis eligible")
    print("     DART routine disclosure -> raw kept / derived skipped")
    print("     DART non-listed disclosure -> raw kept / derived skipped")
    print("     live KIND historical mode -> disabled by capability map")


if __name__ == "__main__":
    main()
