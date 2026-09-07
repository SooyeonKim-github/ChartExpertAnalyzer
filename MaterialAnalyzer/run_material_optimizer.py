from __future__ import annotations

import argparse
from pathlib import Path

from .optimizer import MaterialQualityOptimizer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_DIR = ROOT / "MaterialAnalyzer" / "data" / "history"
DEFAULT_OUTPUT = DEFAULT_HISTORY_DIR / "quality_optimizer"


def main():
    parser = argparse.ArgumentParser(
        description="MaterialQualityOptimizer V1 - catalyst quality audit without return optimization"
    )
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    optimizer = MaterialQualityOptimizer(Path(args.history_dir))
    result = optimizer.run(Path(args.output_dir))

    print("\nMaterialQualityOptimizer finished")
    print(f"event_rows    : {result.event_rows}")
    print(f"score_rows    : {result.score_rows}")
    print(f"linked_rows   : {result.linked_rows}")
    print(f"quality_score : {result.quality_score:.2f}")
    print(f"decision      : {result.decision}")
    print("FORWARD RETURN: NOT USED")
    print("AUTO APPLY    : DISABLED")


if __name__ == "__main__":
    main()
