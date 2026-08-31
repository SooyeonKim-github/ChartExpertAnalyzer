from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as base
from us_market.provider import USYFinanceProvider
from us_market.universe import USUniverseService


base.PykrxDataProvider = USYFinanceProvider
base.TickerUniverseService = USUniverseService
base.RESULT_DIR = Path(__file__).resolve().parent / "results_us"


if __name__ == "__main__":
    args = base.build_parser().parse_args()
    raise SystemExit(args.func(args))
