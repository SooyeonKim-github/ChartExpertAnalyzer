from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from MaterialAnalyzer.news.build_ticker_master import build as build_ticker_master
from MaterialAnalyzer.news.run_article_cluster import run as run_article_cluster
from MaterialAnalyzer.news.run_event_extractor import run as run_event_extractor
from MaterialAnalyzer.news.run_material_scorer import run as run_material_scorer
from MaterialAnalyzer.news.run_novelty_analyzer import run as run_novelty_analyzer
from MaterialAnalyzer.news.run_ticker_linker import run as run_ticker_linker

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

    def _derived(self) -> None:
        print("\n[Derived Pipeline - full deterministic rebuild]")
        run_article_cluster(self.db_path, self.history_dir / "cluster_report.csv", rebuild=True)
        run_event_extractor(self.db_path, self.history_dir / "event_report.csv", rebuild=True)
        # Novelty must be rebuilt only after all events exist. NoveltyRepository orders
        # events by first_seen_at ASC, event_id ASC, preserving point-in-time direction.
        run_novelty_analyzer(self.db_path, self.history_dir / "novelty_report.csv", rebuild=True)
        run_material_scorer(self.db_path, self.history_dir / "material_score_report.csv", rebuild=True)
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
