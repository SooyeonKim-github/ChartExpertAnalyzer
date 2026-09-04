from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ..models import CollectionResult
from .database import Database


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _error_parts(errors: list[str]) -> tuple[str | None, str | None]:
    if not errors:
        return None, None
    message = errors[0]
    code = message.split(":", 1)[0].strip() or "UNKNOWN"
    return code, message[:2000]


class SourceStateRepository:
    """Persist endpoint health and per-run collection history."""

    FAILED_THRESHOLD = 3

    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()

    def begin_run(self, source_id: str, endpoint_id: str, started_at: datetime) -> str:
        run_id = uuid4().hex
        started = _iso(started_at)
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO collection_runs(run_id, source_id, endpoint_id, started_at, status) "
                "VALUES (?, ?, ?, ?, 'RUNNING')",
                (run_id, source_id, endpoint_id, started),
            )
            conn.execute(
                "INSERT INTO source_states(source_id, endpoint_id, last_started_at) VALUES (?, ?, ?) "
                "ON CONFLICT(source_id, endpoint_id) DO UPDATE SET "
                "last_started_at=excluded.last_started_at, updated_at=CURRENT_TIMESTAMP",
                (source_id, endpoint_id, started),
            )
        return run_id

    def finish_run(self, result: CollectionResult) -> tuple[str, int]:
        finished_at = result.finished_at or datetime.now(timezone.utc)
        error_code, error_message = _error_parts(result.errors)

        with self.database.connect() as conn:
            current = conn.execute(
                "SELECT consecutive_failures FROM source_states WHERE source_id = ? AND endpoint_id = ?",
                (result.source_id, result.endpoint_id),
            ).fetchone()
            previous_failures = int(current["consecutive_failures"] or 0) if current else 0

            if result.failed == 0:
                health_status = "HEALTHY"
                consecutive_failures = 0
                run_status = "SUCCESS"
            else:
                consecutive_failures = previous_failures + 1
                health_status = "FAILED" if consecutive_failures >= self.FAILED_THRESHOLD else "DEGRADED"
                processed = result.fetched + result.inserted + result.updated + result.skipped
                run_status = "PARTIAL" if processed > 0 else "FAILED"

            conn.execute(
                "UPDATE collection_runs SET finished_at=?, status=?, health_status=?, discovered=?, fetched=?, "
                "inserted=?, updated=?, duplicated=?, skipped=?, failed=?, checkpoint_value=?, error_code=?, error_message=? "
                "WHERE run_id=?",
                (
                    _iso(finished_at), run_status, health_status, result.discovered, result.fetched,
                    result.inserted, result.updated, result.duplicated, result.skipped, result.failed,
                    result.checkpoint_value, error_code, error_message, result.run_id,
                ),
            )

            conn.execute(
                "INSERT INTO source_states("
                "source_id, endpoint_id, health_status, last_started_at, last_success_at, last_failure_at, "
                "consecutive_failures, last_discovered_count, last_fetched_count, last_inserted_count, "
                "last_updated_count, last_duplicated_count, last_skipped_count, last_failed_count, "
                "last_error_code, last_error_message, checkpoint_value"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source_id, endpoint_id) DO UPDATE SET "
                "health_status=excluded.health_status, "
                "last_started_at=excluded.last_started_at, "
                "last_success_at=COALESCE(excluded.last_success_at, source_states.last_success_at), "
                "last_failure_at=COALESCE(excluded.last_failure_at, source_states.last_failure_at), "
                "consecutive_failures=excluded.consecutive_failures, "
                "last_discovered_count=excluded.last_discovered_count, "
                "last_fetched_count=excluded.last_fetched_count, "
                "last_inserted_count=excluded.last_inserted_count, "
                "last_updated_count=excluded.last_updated_count, "
                "last_duplicated_count=excluded.last_duplicated_count, "
                "last_skipped_count=excluded.last_skipped_count, "
                "last_failed_count=excluded.last_failed_count, "
                "last_error_code=excluded.last_error_code, "
                "last_error_message=excluded.last_error_message, "
                "checkpoint_value=COALESCE(excluded.checkpoint_value, source_states.checkpoint_value), "
                "updated_at=CURRENT_TIMESTAMP",
                (
                    result.source_id,
                    result.endpoint_id,
                    health_status,
                    _iso(result.started_at),
                    _iso(finished_at) if result.failed == 0 else None,
                    _iso(finished_at) if result.failed > 0 else None,
                    consecutive_failures,
                    result.discovered,
                    result.fetched,
                    result.inserted,
                    result.updated,
                    result.duplicated,
                    result.skipped,
                    result.failed,
                    error_code,
                    error_message,
                    result.checkpoint_value,
                ),
            )

        return health_status, consecutive_failures

    def get_state(self, source_id: str, endpoint_id: str):
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT * FROM source_states WHERE source_id = ? AND endpoint_id = ? LIMIT 1",
                (source_id, endpoint_id),
            ).fetchone()
