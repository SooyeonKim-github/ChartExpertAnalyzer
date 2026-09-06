from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from MaterialAnalyzer.news.build_ticker_master import build as build_ticker_master
from MaterialAnalyzer.news.run_article_cluster import run as run_article_cluster
from MaterialAnalyzer.news.run_event_extractor import run as run_event_extractor
from MaterialAnalyzer.news.run_material_scorer import run as run_material_scorer
from MaterialAnalyzer.news.run_novelty_analyzer import run as run_novelty_analyzer
from MaterialAnalyzer.news.run_ticker_linker import run as run_ticker_linker
from MaterialAnalyzer.news.storage import Database

from .dart_prefilter import refresh_existing_dart_prefilter
from .models import HistoricalRangeConfig
from .range_collector import HistoricalRangeCollector
from .reporter import HistoricalMaterialReporter
from .repository import HistoricalRangeRepository


@dataclass
class HistoricalPipelineResult:
    status: str
    failed_chunks: int
    history_rows: int
    backtest_rows: int
    history_csv: Path
    backtest_csv: Path
    coverage_csv: Path


class HistoricalMaterialPipeline:
    def __init__(self, root: str | Path, config: HistoricalRangeConfig):
        self.root = Path(root)
        self.config = config
        self.history_dir = self.root / "MaterialAnalyzer" / "data" / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.history_dir / "material_history.db"
        self.reference_dir = self.root / "MaterialAnalyzer" / "data" / "reference"
        self.state = HistoricalRangeRepository(self.db_path)

    def _prefilter_stats(self):
        database = Database(self.db_path)
        stats = refresh_existing_dart_prefilter(database)
        with database.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS raw_count, "
                "SUM(CASE WHEN COALESCE(analysis_status,'PENDING') NOT LIKE 'SKIP_HISTORY%' THEN 1 ELSE 0 END) AS eligible_count, "
                "SUM(CASE WHEN analysis_status='SKIP_HISTORY_ROUTINE' THEN 1 ELSE 0 END) AS routine_count, "
                "SUM(CASE WHEN analysis_status='SKIP_HISTORY_NONLISTED' THEN 1 ELSE 0 END) AS nonlisted_count "
                "FROM articles"
            ).fetchone()
        print(
            "[HistoricalAnalysisPrefilter] "
            f"DART_raw={stats.get('TOTAL_ROWS', 0):,} reclassified={stats.get('UPDATED_ROWS', 0):,} "
            f"all_raw={int(row['raw_count'] or 0):,} eligible={int(row['eligible_count'] or 0):,} "
            f"routine_skip={int(row['routine_count'] or 0):,} nonlisted_skip={int(row['nonlisted_count'] or 0):,}"
        )
        return int(row["eligible_count"] or 0)

    def _derived(self) -> None:
        print("\n[Derived Pipeline - full deterministic rebuild]")
        eligible_count = self._prefilter_stats()
        print(f"\n[1/5] ArticleCluster eligible_articles={eligible_count:,}")
        run_article_cluster(
            self.db_path,
            self.history_dir / "cluster_report.csv",
            rebuild=True,
            progress_every=5000,
        )
        print("\n[2/5] EventExtractor")
        run_event_extractor(self.db_path, self.history_dir / "event_report.csv", rebuild=True)
        print("\n[3/5] NoveltyAnalyzer - chronological rebuild")
        run_novelty_analyzer(self.db_path, self.history_dir / "novelty_report.csv", rebuild=True)
        print("\n[4/5] MaterialScorer")
        run_material_scorer(self.db_path, self.history_dir / "material_score_report.csv", rebuild=True)
        print("\n[5/5] TickerLinker")
        try:
            build_ticker_master(if_stale_days=7, best_effort=True)
        except Exception as exc:
            print(f"[WARN] ticker master refresh before historical link skipped: {type(exc).__name__}: {exc}")
        run_ticker_linker(
            self.db_path,
            self.reference_dir,
            self.history_dir / "ticker_link_report.csv",
            self.history_dir / "ticker_link_unresolved.csv",
            rebuild=True,
        )

    def run(self, *, collect: bool = True, reprocess_derived: bool = True) -> HistoricalPipelineResult:
        run_id = self.state.begin_run(self.config)
        failed_chunks = 0
        try:
            if collect:
                collector = HistoricalRangeCollector(self.db_path, self.config)
                summary = collector.run()
                failed_chunks = summary.failed_chunks
                print(
                    "\nCOLLECTION TOTAL "
                    f"complete_chunks={summary.complete_chunks} skipped_chunks={summary.skipped_chunks} "
                    f"failed_chunks={summary.failed_chunks} discovered={summary.discovered} "
                    f"inserted={summary.inserted} updated={summary.updated} failed={summary.failed}"
                )
            if reprocess_derived:
                self._derived()

            reporter = HistoricalMaterialReporter(
                self.db_path,
                self.config.requested_start,
                self.config.requested_end,
            )
            history_csv, backtest_csv, history_rows, backtest_rows = reporter.export(
                self.history_dir / "material_history.csv",
                self.history_dir / "material_history_backtest.csv",
            )
            coverage_csv = self.state.export_coverage(self.history_dir / "historical_source_coverage.csv")
            status = "PARTIAL" if failed_chunks else "COMPLETE"
            self.state.finish_run(run_id, status)
            return HistoricalPipelineResult(
                status=status,
                failed_chunks=failed_chunks,
                history_rows=history_rows,
                backtest_rows=backtest_rows,
                history_csv=history_csv,
                backtest_csv=backtest_csv,
                coverage_csv=coverage_csv,
            )
        except Exception as exc:
            self.state.finish_run(run_id, "FAILED", f"{type(exc).__name__}: {exc}")
            raise
