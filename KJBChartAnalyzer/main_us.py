from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import _print_errors, _print_screen, _save_confirmed_charts, _save_universe
from chartsel.analysis.analyzer import ChartAnalyzer
from chartsel.config import load_config
from chartsel.reporting.agent_exporter import export_agent_candidates
from chartsel.reporting.html_report import save_screen_html
from chartsel.reporting.report import save_screen_csv
from chartsel.selection.selector import StockSelector
import chartsel.selection.selector as selector_module

from us_market.provider import USYFinanceProvider
from us_market.universe import USUniverseService


HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="KJB chart screen for current US market-cap universe")
    p.add_argument("--universe-csv", required=True)
    p.add_argument("--top-n", type=int, default=300)
    p.add_argument("--period", default="5y")
    p.add_argument("--agent-top-n", type=int, default=30)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--config", default=None)
    p.add_argument("--output-dir", default=str(HERE / "output_us"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = copy.deepcopy(load_config(args.config))
    # KR sector-flow context is not transferable to the US universe.
    cfg.setdefault("sector_strength", {})["enabled"] = False

    provider = USYFinanceProvider(use_cache=not args.no_cache)
    analyzer = ChartAnalyzer(cfg)
    selector = StockSelector(analyzer, provider, cfg)
    universe = USUniverseService(args.universe_csv).get_universe(
        top_n=args.top_n, sort_by="market_cap", include_etf=False
    )

    # StockSelector's default benchmark helper is KR-only. Patch it in this
    # process only; domestic code/files remain untouched.
    selector_module._benchmark_for_market = lambda market: "^GSPC"

    print("=" * 72)
    print("KJB US Stock Screening")
    print("=" * 72)
    print(f"Universe : current US market-cap TOP {len(universe)}")
    print("Benchmark: S&P 500 (^GSPC)")
    print("Sector   : KR sector-flow module disabled")
    print()

    table, errors = selector.screen_universe(universe, period=args.period, limit=0)
    _print_screen(table, with_meta=True)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    universe_out = out_dir / "top300_universe.csv"
    screen_out = out_dir / "top300_screen.csv"
    report_out = out_dir / "top300_screen.html"

    _save_universe(universe, str(universe_out))
    save_screen_csv(table, str(screen_out))
    save_screen_html(table, str(report_out))
    _save_confirmed_charts(table, selector, analyzer, out_dir / "confirmed_charts")
    agent_json, agent_md = export_agent_candidates(table, out_dir, args.agent_top_n)

    print(f"Agent JSON: {agent_json}")
    print(f"Agent MD  : {agent_md}")
    _print_errors(errors)
    print(f"[DONE] {screen_out}")
    return 0 if not table.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
