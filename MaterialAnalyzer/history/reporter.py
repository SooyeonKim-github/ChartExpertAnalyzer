from __future__ import annotations

import csv
from pathlib import Path

from MaterialAnalyzer.news.storage import Database


FIELDS = [
    "market_date","published_at","published_at_precision","event_id","ticker","name",
    "event_type","event_stage","event_title","material_score","material_status",
    "relation_type","relation_weight","mapping_relevance","ticker_material_score",
    "novelty_status","novelty_score","positive_negative","theme","theme_materiality_score",
    "source_id","source_count","coverage_status","context_only","backtest_eligible","eligibility_reason",
]


class HistoricalMaterialReporter:
    def __init__(self, db_path: str | Path, requested_start, requested_end):
        self.database = Database(db_path)
        self.requested_start = requested_start.strftime("%Y%m%d")
        self.requested_end = requested_end.strftime("%Y%m%d")

    def _rows(self):
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT e.market_date,a.published_at,a.published_at_precision,e.event_id,l.ticker,l.name,"
                "e.event_type,e.event_stage,e.event_title,s.material_score,s.material_status,"
                "l.relation_type,l.relation_weight,l.mapping_relevance,l.ticker_material_score,"
                "n.novelty_status,n.novelty_score,e.positive_negative,l.theme,l.theme_materiality_score,"
                "e.original_source_id AS source_id,e.source_count,COALESCE(c.status,'UNKNOWN') AS coverage_status "
                "FROM material_ticker_links l "
                "JOIN material_events e ON e.event_id=l.event_id "
                "JOIN material_scores s ON s.event_id=e.event_id "
                "LEFT JOIN event_novelty n ON n.event_id=e.event_id "
                "LEFT JOIN articles a ON a.article_id=e.representative_article_id "
                "LEFT JOIN historical_source_coverage c ON c.source_id=e.original_source_id AND c.coverage_date=a.published_date "
                "ORDER BY COALESCE(e.market_date,''),COALESCE(e.first_seen_at,''),e.event_id,l.ticker"
            ).fetchall()

    def _record(self, row):
        market_date = row["market_date"] or ""
        in_requested = bool(market_date and self.requested_start <= market_date <= self.requested_end)
        context_only = bool(market_date and market_date < self.requested_start)
        reason = ""
        eligible = in_requested
        if not row["published_at"]:
            eligible = False
            reason = "PUBLISHED_AT_UNKNOWN"
        elif not market_date:
            eligible = False
            reason = "MARKET_DATE_UNKNOWN"
        elif row["coverage_status"] == "FAILED":
            eligible = False
            reason = "SOURCE_COVERAGE_FAILED"
        elif not in_requested:
            eligible = False
            reason = "CONTEXT_ONLY" if context_only else "OUTSIDE_REQUESTED_RANGE"
        return {
            "market_date":market_date,
            "published_at":row["published_at"] or "",
            "published_at_precision":row["published_at_precision"] or "UNKNOWN",
            "event_id":row["event_id"], "ticker":row["ticker"], "name":row["name"],
            "event_type":row["event_type"], "event_stage":row["event_stage"], "event_title":row["event_title"],
            "material_score":row["material_score"], "material_status":row["material_status"],
            "relation_type":row["relation_type"], "relation_weight":row["relation_weight"],
            "mapping_relevance":row["mapping_relevance"], "ticker_material_score":row["ticker_material_score"],
            "novelty_status":row["novelty_status"] or "", "novelty_score":row["novelty_score"] if row["novelty_score"] is not None else "",
            "positive_negative":row["positive_negative"], "theme":row["theme"] or "",
            "theme_materiality_score":row["theme_materiality_score"], "source_id":row["source_id"] or "",
            "source_count":row["source_count"], "coverage_status":row["coverage_status"],
            "context_only":int(context_only), "backtest_eligible":int(eligible), "eligibility_reason":reason,
        }

    @staticmethod
    def _write(path: Path, records) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(records)
        return path

    def export(self, history_path: str | Path, backtest_path: str | Path):
        records = [self._record(row) for row in self._rows()]
        history = self._write(Path(history_path), records)
        backtest = self._write(Path(backtest_path), [row for row in records if row["backtest_eligible"]])
        return history, backtest, len(records), sum(int(row["backtest_eligible"]) for row in records)
