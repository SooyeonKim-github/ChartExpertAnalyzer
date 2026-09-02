from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from config import DEFAULT_INFO_EXCEL

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import ExcelUniverseService, exclude_etf_rows  # noqa: E402


@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    name: str
    market: str


class TickerUniverse:
    def __init__(self, info_excel: str | Path = DEFAULT_INFO_EXCEL):
        self.info_excel = Path(info_excel)
        self._shared = ExcelUniverseService(self.info_excel)

    def load(self):
        out = self._shared.load_universe_df().copy()
        if __import__("os").environ.get("INCLUDE_ETF", "").strip() != "1":
            out = exclude_etf_rows(out)
        out["Market"] = out["market"]
        return out

    def get(self, top_n=0, sort_by="market_cap"):
        infos = self._shared.get_universe(top_n=top_n, sort_by=sort_by, include_etf=False)
        return [TickerInfo(i.ticker, i.name, i.market) for i in infos]
