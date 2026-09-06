from __future__ import annotations

import csv
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from MaterialAnalyzer.news.storage import Database
from .models import HistoricalRangeConfig, RangeChunk


HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_range_runs (
    run_id TEXT PRIMARY KEY,
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    context_start TEXT NOT NULL,
    warmup_days INTEGER NOT NULL,
    chunk_days INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS historical_range_chunks (
    source_id TEXT NOT NULL,
    chunk_start TEXT NOT NULL,
    chunk_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    discovered INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at TEXT,
    completed_at TEXT,
    PRIMARY KEY(source_id, chunk_start, chunk_end)
);
CREATE INDEX IF NOT EXISTS idx_history_chunks_status
ON historical_range_chunks(status, source_id, chunk_start);
CREATE TABLE IF NOT EXISTS historical_source_coverage (
    source_id TEXT NOT NULL,
    coverage_date TEXT NOT NULL,
    status TEXT NOT NULL,
    discovered INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source_id, coverage_date)
);
CREATE INDEX IF NOT EXISTS idx_history_coverage_date
ON historical_source_coverage(coverage_date, status);
"""


class HistoricalRangeRepository:
    def __init__(self, db_path: str | Path):
        self.database = Database(db_path)
        self.database.initialize()
        with self.database.connect() as conn:
            conn.executescript(HISTORY_SCHEMA)

    def begin_run(self, config: HistoricalRangeConfig) -> str:
        run_id = "HIST_" + uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO historical_range_runs(run_id,requested_start,requested_end,context_start,warmup_days,chunk_days,status,started_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (run_id, config.requested_start.isoformat(), config.requested_end.isoformat(),
                 config.context_start.isoformat(), config.warmup_days, config.chunk_days, "RUNNING", now),
            )
        return run_id

    def finish_run(self, run_id: str, status: str, error_message: str = "") -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE historical_range_runs SET status=?, finished_at=?, error_message=? WHERE run_id=?",
                (status, datetime.now(timezone.utc).isoformat(), error_message or None, run_id),
            )

    def is_complete(self, chunk: RangeChunk) -> bool:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT status FROM historical_range_chunks WHERE source_id=? AND chunk_start=? AND chunk_end=?",
                chunk.key,
            ).fetchone()
        return bool(row and row["status"] == "COMPLETE")

    def mark_running(self, chunk: RangeChunk) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO historical_range_chunks(source_id,chunk_start,chunk_end,status,attempt_count,started_at) "
                "VALUES (?,?,?,'RUNNING',1,?) ON CONFLICT(source_id,chunk_start,chunk_end) DO UPDATE SET "
                "status='RUNNING',attempt_count=historical_range_chunks.attempt_count+1,started_at=excluded.started_at,last_error=NULL",
                (*chunk.key, now),
            )

    def mark_result(self, chunk: RangeChunk, result, *, error: str = "") -> None:
        status = "FAILED" if error else "COMPLETE"
        now = datetime.now(timezone.utc).isoformat()
        discovered = int(getattr(result, "discovered", 0) or 0) if result is not None else 0
        inserted = int(getattr(result, "inserted", 0) or 0) if result is not None else 0
        updated = int(getattr(result, "updated", 0) or 0) if result is not None else 0
        skipped = int(getattr(result, "skipped", 0) or 0) if result is not None else 0
        failed = int(getattr(result, "failed", 0) or 0) if result is not None else 1
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE historical_range_chunks SET status=?,discovered=?,inserted=?,updated=?,skipped=?,failed=?,last_error=?,completed_at=? "
                "WHERE source_id=? AND chunk_start=? AND chunk_end=?",
                (status, discovered, inserted, updated, skipped, failed, error or None, now, *chunk.key),
            )
        self.mark_coverage_range(
            chunk.source_id, chunk.start, chunk.end, status="FAILED" if error else "OK",
            discovered=discovered, inserted=inserted, failed=failed, note=error,
        )

    def mark_coverage_range(self, source_id: str, start: date, end: date, *, status: str,
                            discovered: int = 0, inserted: int = 0, failed: int = 0, note: str = "") -> None:
        current = start
        days = max(1, (end - start).days + 1)
        while current <= end:
            with self.database.connect() as conn:
                conn.execute(
                    "INSERT INTO historical_source_coverage(source_id,coverage_date,status,discovered,inserted,failed,note) "
                    "VALUES (?,?,?,?,?,?,?) ON CONFLICT(source_id,coverage_date) DO UPDATE SET "
                    "status=excluded.status,discovered=excluded.discovered,inserted=excluded.inserted,failed=excluded.failed,note=excluded.note,updated_at=CURRENT_TIMESTAMP",
                    (source_id, current.isoformat(), status, discovered // days, inserted // days, failed, note or None),
                )
            current = date.fromordinal(current.toordinal() + 1)

    def export_coverage(self, output: str | Path) -> Path:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT source_id,coverage_date,status,discovered,inserted,failed,note FROM historical_source_coverage "
                "ORDER BY coverage_date,source_id"
            ).fetchall()
        with path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["source_id","date","status","discovered","inserted","failed","note"])
            for row in rows:
                writer.writerow([row["source_id"],row["coverage_date"],row["status"],row["discovered"],row["inserted"],row["failed"],row["note"] or ""])
        return path
