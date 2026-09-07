from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import MaterialBacktester


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "MaterialAnalyzer" / "data" / "history" / "material_history_backtest.csv"
DEFAULT_OUTPUT = ROOT / "MaterialAnalyzer" / "data" / "history" / "backtest"


def main():
    parser = argparse.ArgumentParser(description="MaterialBacktester V1.1")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    backtester = MaterialBacktester()
    result = backtester.run(Path(args.input), Path(args.output_dir), limit=args.limit)

    print("\nMaterialBacktester finished")
    print(f"input_rows         : {result.input_rows}")
    print(f"result_rows        : {result.result_rows}")
    print(f"valid_entry_rows   : {result.valid_entry_rows}")
    print(f"failed_price_rows  : {result.failed_price_rows}")
    print(f"ticker_day_results : {result.ticker_day_results_csv}")
    print(f"error_summary      : {result.error_summary_csv}")


if __name__ == "__main__":
    main()
