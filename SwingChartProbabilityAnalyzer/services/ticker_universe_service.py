from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from config import INFO_EXCEL_PATH

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import ExcelUniverseService  # noqa: E402


@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    name: str
    market: str


class TickerUniverseService:
    def __init__(self, info_excel_path: str | Path = INFO_EXCEL_PATH) -> None:
        self._shared = ExcelUniverseService(info_excel_path)
        self.info_excel_path = Path(info_excel_path)

    def load_universe_df(self):
        return self._shared.load_universe_df()

    def get_universe(self, top_n: int = 0, sort_by: str = "market_cap", include_etf: bool = False) -> List[TickerInfo]:
        infos = self._shared.get_universe(top_n=top_n, sort_by=sort_by, include_etf=include_etf)
        return [TickerInfo(i.ticker, i.name, i.market) for i in infos]
