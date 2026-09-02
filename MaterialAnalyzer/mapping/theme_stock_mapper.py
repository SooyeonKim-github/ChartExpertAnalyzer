from __future__ import annotations

import csv
from pathlib import Path

from ..analysis_models import StockThemeMatch


class ThemeStockMapper:
    """Map a normalized theme to editable stock relationships from CSV."""

    def __init__(self, mapping_file: Path) -> None:
        self.mapping_file = mapping_file
        self.rows = self._load(mapping_file)

    def map(self, theme: str) -> list[StockThemeMatch]:
        rows = [row for row in self.rows if row.theme == theme]
        rows.sort(key=lambda row: (-row.relevance, row.ticker))
        return rows

    @staticmethod
    def _load(path: Path) -> list[StockThemeMatch]:
        if not path.exists():
            return []
        out: list[StockThemeMatch] = []
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                enabled = str(row.get("enabled", "1")).strip().lower()
                if enabled in {"0", "false", "n", "no"}:
                    continue
                theme = str(row.get("theme", "")).strip()
                ticker_raw = str(row.get("ticker", "")).strip()
                name = str(row.get("name", "")).strip()
                relation_type = str(row.get("relation_type", "DIRECT")).strip().upper() or "DIRECT"
                reason = str(row.get("reason", "")).strip()
                try:
                    relevance = float(row.get("relevance", 0.0))
                except (TypeError, ValueError):
                    continue
                if not theme or not ticker_raw or not name:
                    continue
                ticker = ticker_raw.zfill(6)
                out.append(
                    StockThemeMatch(
                        theme=theme,
                        ticker=ticker,
                        name=name,
                        relevance=max(0.0, min(relevance, 1.0)),
                        relation_type=relation_type,
                        reason=reason,
                    )
                )
        return out
