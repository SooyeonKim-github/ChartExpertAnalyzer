from __future__ import annotations

import argparse
from pathlib import Path

from .optimizer import MaterialThresholdOptimizer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "MaterialAnalyzer" / "data" / "history" / "backtest" / "material_backtest_results.csv"
DEFAULT_OUTPUT = ROOT / "MaterialAnalyzer" / "data" / "history" / "optimizer"


def main():
    parser = argparse.ArgumentParser(description="MaterialThresholdOptimizer V1")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-sample", type=int, default=100)
    parser.add_argument("--train-end", default="", help="optional YYYYMMDD train end")
    parser.add_argument("--validation-start", default="", help="optional YYYYMMDD validation start")
    args = parser.parse_args()

    optimizer = MaterialThresholdOptimizer(min_sample=args.min_sample)
    result = optimizer.run(
        Path(args.input),
        Path(args.output_dir),
        train_end=args.train_end.strip() or None,
        validation_start=args.validation_start.strip() or None,
    )
    print("\nMaterialThresholdOptimizer finished")
    print(f"input_rows      : {result.input_rows}")
    print(f"train_rows      : {result.train_rows}")
    print(f"validation_rows : {result.validation_rows}")
    print("AUTO APPLY      : DISABLED")


if __name__ == "__main__":
    main()
