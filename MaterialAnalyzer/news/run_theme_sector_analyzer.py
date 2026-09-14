from __future__ import annotations

import argparse
from pathlib import Path

from .storage import Database
from .theme_sector import MasterCatalog, RuleClassifier, ThemeSectorAnalyzer, ThemeSectorReporter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "news.db"
DEFAULT_SECTOR_MASTER = ROOT / "data" / "reference" / "sector_master.yaml"
DEFAULT_THEME_MASTER = ROOT / "data" / "reference" / "theme_master.yaml"
DEFAULT_REPORT = ROOT / "data" / "theme_sector_report.csv"
DEFAULT_SUMMARY = ROOT / "data" / "theme_daily_summary.csv"


def run(
    db_path: Path = DEFAULT_DB,
    output_path: Path = DEFAULT_REPORT,
    summary_path: Path = DEFAULT_SUMMARY,
    *,
    sector_master_path: Path = DEFAULT_SECTOR_MASTER,
    theme_master_path: Path = DEFAULT_THEME_MASTER,
    end_date: str | None = None,
    days: int = 7,
    limit: int | None = None,
    include_sector_only: bool = False,
):
    catalog = MasterCatalog.load(sector_master_path, theme_master_path)
    classifier = RuleClassifier(catalog)
    analyzer = ThemeSectorAnalyzer(Database(db_path), classifier)
    reporter = ThemeSectorReporter()

    print("=" * 80)
    print(" ThemeSectorAnalyzer V1 - Rule Based Market Theme/Sector Materials")
    print(" Ticker Linking / Embedding: DISABLED")
    print("=" * 80)
    print(f"DB            : {db_path}")
    print(f"Sector Master : {sector_master_path}")
    print(f"Theme Master  : {theme_master_path}")
    print(f"Days          : {days}")
    print(f"End Date      : {end_date or 'LATEST'}")
    print("-" * 80)

    stats, rows = analyzer.run(
        end_date=end_date,
        days=days,
        limit=limit,
        include_sector_only=include_sector_only,
    )
    detail_report = reporter.export_detail(rows, output_path)
    summary_report = reporter.export_daily_summary(rows, summary_path)

    print(f"range                = {stats.start_date or '-'} ~ {stats.end_date or '-'}")
    print(f"clusters_scanned     = {stats.clusters_scanned}")
    print(f"clusters_with_theme  = {stats.clusters_with_theme}")
    print(f"theme_matches        = {stats.theme_matches}")
    print(f"sector_only_clusters = {stats.sector_only_clusters}")
    print(f"detail_report        = {detail_report}")
    print(f"daily_summary        = {summary_report}")
    print("=" * 80)
    return stats, rows


def main():
    parser = argparse.ArgumentParser(
        description="ThemeSectorAnalyzer V1 - deterministic rule-based market material analyzer"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--sector-master", default=str(DEFAULT_SECTOR_MASTER))
    parser.add_argument("--theme-master", default=str(DEFAULT_THEME_MASTER))
    parser.add_argument("--date", default=None, help="End market date YYYYMMDD; default latest")
    parser.add_argument("--days", type=int, default=7, help="Calendar-day lookback including end date")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--include-sector-only",
        action="store_true",
        help="Also export clusters with sector evidence but no matched theme",
    )
    args = parser.parse_args()

    run(
        Path(args.db),
        Path(args.output),
        Path(args.summary_output),
        sector_master_path=Path(args.sector_master),
        theme_master_path=Path(args.theme_master),
        end_date=args.date,
        days=args.days,
        limit=args.limit,
        include_sector_only=args.include_sector_only,
    )


if __name__ == "__main__":
    main()
