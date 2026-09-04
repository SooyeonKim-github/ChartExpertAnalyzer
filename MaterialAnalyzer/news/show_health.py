from __future__ import annotations

import argparse
from pathlib import Path

from .storage import Database


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"


def run(db_path: Path = DEFAULT_DB, recent_runs: int = 0):
    database = Database(db_path)
    database.initialize()

    with database.connect() as conn:
        states = conn.execute(
            "SELECT source_id, endpoint_id, health_status, consecutive_failures, "
            "last_success_at, last_failure_at, last_discovered_count, last_fetched_count, "
            "last_inserted_count, last_updated_count, last_skipped_count, last_failed_count "
            "FROM source_states ORDER BY endpoint_id"
        ).fetchall()

        print("=" * 108)
        print(" NewsCollector Source Health")
        print("=" * 108)
        if not states:
            print("No source health history yet. Run NewsCollector first.")
        else:
            print(
                f"{'ENDPOINT':<22} {'HEALTH':<10} {'FAIL#':>5} "
                f"{'FOUND':>6} {'FETCH':>6} {'NEW':>5} {'UPD':>5} {'SKIP':>6} {'FAIL':>5}"
            )
            print("-" * 108)
            for row in states:
                print(
                    f"{row['endpoint_id']:<22} {row['health_status']:<10} "
                    f"{row['consecutive_failures']:>5} {row['last_discovered_count']:>6} "
                    f"{row['last_fetched_count']:>6} {row['last_inserted_count']:>5} "
                    f"{row['last_updated_count']:>5} {row['last_skipped_count']:>6} "
                    f"{row['last_failed_count']:>5}"
                )
        print("=" * 108)

        if recent_runs > 0:
            runs = conn.execute(
                "SELECT started_at, endpoint_id, status, health_status, discovered, fetched, "
                "inserted, updated, skipped, failed, error_code "
                "FROM collection_runs ORDER BY started_at DESC LIMIT ?",
                (recent_runs,),
            ).fetchall()
            print()
            print(f"Recent collection runs: {len(runs)}")
            print("-" * 108)
            for row in runs:
                print(
                    f"{row['started_at']} {row['endpoint_id']:<22} "
                    f"status={row['status']:<7} health={row['health_status'] or '-':<8} "
                    f"found={row['discovered']} fetch={row['fetched']} new={row['inserted']} "
                    f"upd={row['updated']} skip={row['skipped']} fail={row['failed']} "
                    f"error={row['error_code'] or '-'}"
                )


def main():
    parser = argparse.ArgumentParser(description="Show NewsCollector source health and run history")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--runs", type=int, default=0, help="Also show N most recent collection runs")
    args = parser.parse_args()
    run(Path(args.db), recent_runs=max(0, args.runs))


if __name__ == "__main__":
    main()
