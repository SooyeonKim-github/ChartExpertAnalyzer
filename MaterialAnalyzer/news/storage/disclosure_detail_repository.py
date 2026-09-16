from __future__ import annotations

import csv
import json
from pathlib import Path

from ..disclosure_detail.models import DisclosureDetailRecord
from .database import Database


DISCLOSURE_DETAIL_SCHEMA = """
CREATE TABLE IF NOT EXISTS disclosure_details (
    event_id TEXT PRIMARY KEY,
    rcept_no TEXT,
    detail_type TEXT NOT NULL,
    detail_event_key TEXT,
    source_document_name TEXT,
    contract_amount REAL,
    recent_sales REAL,
    sales_ratio REAL,
    counterparty TEXT,
    contract_subject TEXT,
    contract_start_date TEXT,
    contract_end_date TEXT,
    correction_before_json TEXT,
    correction_after_json TEXT,
    raw_detail_json TEXT,
    parse_status TEXT NOT NULL,
    parse_confidence REAL NOT NULL DEFAULT 0,
    error_message TEXT,
    parser_version TEXT NOT NULL,
    event_updated_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_disclosure_details_rcept ON disclosure_details(rcept_no);
CREATE INDEX IF NOT EXISTS idx_disclosure_details_key ON disclosure_details(detail_event_key);
CREATE INDEX IF NOT EXISTS idx_disclosure_details_status ON disclosure_details(parse_status);
"""


class DisclosureDetailRepository:
    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()
        with self.database.connect() as conn:
            conn.executescript(DISCLOSURE_DETAIL_SCHEMA)

    def clear_all(self):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM disclosure_details")

    def prune_orphans(self):
        with self.database.connect() as conn:
            conn.execute(
                "DELETE FROM disclosure_details WHERE event_id NOT IN (SELECT event_id FROM material_events)"
            )

    def get_pending_events(self, *, parser_version: str, limit: int | None = None):
        sql = (
            "SELECT e.*,a.external_id AS rcept_no FROM material_events e "
            "JOIN articles a ON a.article_id=e.representative_article_id "
            "LEFT JOIN disclosure_details d ON d.event_id=e.event_id "
            "WHERE e.original_source_id='DART' AND e.event_type='ORDER_CONTRACT' "
            "AND COALESCE(a.external_id,'') <> '' "
            "AND (d.event_id IS NULL OR d.parser_version <> ? "
            "OR COALESCE(d.event_updated_at,'') <> COALESCE(e.updated_at,'')) "
            "ORDER BY e.market_date DESC,COALESCE(e.first_seen_at,e.created_at) DESC,e.event_id DESC"
        )
        params: list[object] = [parser_version]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def upsert(self, record: DisclosureDetailRecord) -> str:
        with self.database.connect() as conn:
            existed = conn.execute(
                "SELECT 1 FROM disclosure_details WHERE event_id=? LIMIT 1",
                (record.event_id,),
            ).fetchone() is not None
            conn.execute(
                "INSERT INTO disclosure_details("
                "event_id,rcept_no,detail_type,detail_event_key,source_document_name,contract_amount,recent_sales,"
                "sales_ratio,counterparty,contract_subject,contract_start_date,contract_end_date,"
                "correction_before_json,correction_after_json,raw_detail_json,parse_status,parse_confidence,"
                "error_message,parser_version,event_updated_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "rcept_no=excluded.rcept_no,detail_type=excluded.detail_type,detail_event_key=excluded.detail_event_key,"
                "source_document_name=excluded.source_document_name,contract_amount=excluded.contract_amount,"
                "recent_sales=excluded.recent_sales,sales_ratio=excluded.sales_ratio,counterparty=excluded.counterparty,"
                "contract_subject=excluded.contract_subject,contract_start_date=excluded.contract_start_date,"
                "contract_end_date=excluded.contract_end_date,correction_before_json=excluded.correction_before_json,"
                "correction_after_json=excluded.correction_after_json,raw_detail_json=excluded.raw_detail_json,"
                "parse_status=excluded.parse_status,parse_confidence=excluded.parse_confidence,"
                "error_message=excluded.error_message,parser_version=excluded.parser_version,"
                "event_updated_at=excluded.event_updated_at,updated_at=CURRENT_TIMESTAMP",
                (
                    record.event_id,record.rcept_no,record.detail_type,record.detail_event_key,record.source_document_name,
                    record.contract_amount,record.recent_sales,record.sales_ratio,record.counterparty,
                    record.contract_subject,record.contract_start_date,record.contract_end_date,
                    json.dumps(record.correction_before,ensure_ascii=False),
                    json.dumps(record.correction_after,ensure_ascii=False),
                    json.dumps(record.raw_detail,ensure_ascii=False),record.parse_status,record.parse_confidence,
                    record.error_message,record.parser_version,record.event_updated_at,
                ),
            )
        return "UPDATED" if existed else "INSERTED"

    def count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS cnt FROM disclosure_details").fetchone()["cnt"])

    def export_report(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT d.*,e.market_date,e.event_title,e.companies_json,e.stock_codes_json "
                "FROM disclosure_details d JOIN material_events e ON e.event_id=d.event_id "
                "ORDER BY e.market_date DESC,e.event_id ASC"
            ).fetchall()
        fields = [
            "event_id","rcept_no","market_date","detail_type","detail_event_key","parse_status","parse_confidence",
            "contract_amount","recent_sales","sales_ratio","counterparty","contract_subject","contract_start_date",
            "contract_end_date","correction_before","correction_after","source_document_name","companies","stock_codes",
            "event_title","error_message","parser_version",
        ]
        with output.open("w",encoding="utf-8-sig",newline="") as fp:
            writer = csv.DictWriter(fp,fieldnames=fields)
            writer.writeheader()
            for row in rows:
                def jpipe(value):
                    if not value:
                        return ""
                    try:
                        parsed = json.loads(value)
                    except (TypeError,json.JSONDecodeError):
                        return str(value)
                    if isinstance(parsed,list):
                        return "|".join(str(x) for x in parsed)
                    return json.dumps(parsed,ensure_ascii=False)
                writer.writerow({
                    "event_id":row["event_id"],"rcept_no":row["rcept_no"],"market_date":row["market_date"],
                    "detail_type":row["detail_type"],"detail_event_key":row["detail_event_key"],
                    "parse_status":row["parse_status"],"parse_confidence":row["parse_confidence"],
                    "contract_amount":row["contract_amount"],"recent_sales":row["recent_sales"],
                    "sales_ratio":row["sales_ratio"],"counterparty":row["counterparty"],
                    "contract_subject":row["contract_subject"],"contract_start_date":row["contract_start_date"],
                    "contract_end_date":row["contract_end_date"],"correction_before":jpipe(row["correction_before_json"]),
                    "correction_after":jpipe(row["correction_after_json"]),"source_document_name":row["source_document_name"],
                    "companies":jpipe(row["companies_json"]),"stock_codes":jpipe(row["stock_codes_json"]),
                    "event_title":row["event_title"],"error_message":row["error_message"],
                    "parser_version":row["parser_version"],
                })
        return output
