from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
for p in (REPO_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ThresholdOptimization import ThresholdOptimizer  # noqa: E402
from optimization import DynamicThresholdAdapter  # noqa: E402


def _latest_range_file() -> Path:
    files = list((BASE_DIR / "results").glob("range_*/dynamic_range_events.csv"))
    if not files:
        raise FileNotFoundError("No dynamic_range_events.csv found. Run run_dynamic_range.bat first.")
    return max(files, key=lambda p: (p.parent.name, p.stat().st_mtime))


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def main() -> None:
    p = argparse.ArgumentParser(description="Dynamic purged walk-forward threshold optimizer")
    p.add_argument("--range-file")
    p.add_argument("--optimizer-config", default="threshold_optimizer.yaml")
    p.add_argument("--current-confirmed-score", type=float, default=70.0)
    p.add_argument("--out")
    args = p.parse_args()

    range_file = _resolve(args.range_file, _latest_range_file())
    optimizer_cfg = yaml.safe_load(
        _resolve(args.optimizer_config, BASE_DIR / "threshold_optimizer.yaml").read_text(encoding="utf-8")
    ) or {}
    df = pd.read_csv(range_file, encoding="utf-8-sig", dtype={"ticker": str})
    out_dir = _resolve(args.out, range_file.parent / "optimizer")

    adapter = DynamicThresholdAdapter(
        phase="confirmed",
        analyzer_config={"confirmed_score": float(args.current_confirmed_score)},
    )
    result = ThresholdOptimizer(adapter, optimizer_cfg).run(df)
    result.write(out_dir / "confirmed")
    result.current_vs_optimized.to_csv(
        out_dir / "current_vs_optimized.csv", index=False, encoding="utf-8-sig"
    )
    (out_dir / "recommended_thresholds.yaml").write_text(
        yaml.safe_dump(result.recommended_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print("\n============================================")
    print(" Dynamic Threshold Optimizer complete")
    print("============================================")
    print(f"Input : {range_file}")
    print(f"Output: {out_dir}")
    print(f"Recommended: {result.recommended_params}")
    print("Lecture RSI/MACD/Ichimoku and 1:2:7 are not optimized.")
    print("NOTE: recommendation is not applied to main_range.py defaults automatically.")


if __name__ == "__main__":
    main()
