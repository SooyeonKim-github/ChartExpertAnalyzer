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
from chartsel.config import load_config  # noqa: E402
from optimization import KJBThresholdAdapter  # noqa: E402


def _latest_range_file() -> Path:
    files = list((BASE_DIR / "results").glob("range_*/chart_range_events.csv"))
    if not files:
        raise FileNotFoundError("No KJB chart_range_events.csv found. Run the KJB range backtest first.")
    return max(files, key=lambda p: (p.parent.name, p.stat().st_mtime))


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def main() -> None:
    p = argparse.ArgumentParser(description="KJB purged walk-forward threshold optimizer")
    p.add_argument("--range-file")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--optimizer-config", default="config/threshold_optimizer.yaml")
    p.add_argument("--out")
    args = p.parse_args()

    range_file = _resolve(args.range_file, _latest_range_file())
    cfg = load_config(str(_resolve(args.config, BASE_DIR / "config/default.yaml")))
    optimizer_cfg = yaml.safe_load(
        _resolve(args.optimizer_config, BASE_DIR / "config/threshold_optimizer.yaml").read_text(encoding="utf-8")
    ) or {}

    df = pd.read_csv(range_file, encoding="utf-8-sig", dtype={"ticker": str})
    out_dir = _resolve(args.out, range_file.parent / "optimizer")

    adapter = KJBThresholdAdapter(phase="confirmed", analyzer_config=cfg)
    result = ThresholdOptimizer(adapter, optimizer_cfg).run(df)
    paths = result.write(out_dir / "confirmed")
    result.current_vs_optimized.to_csv(out_dir / "current_vs_optimized.csv", index=False, encoding="utf-8-sig")
    (out_dir / "recommended_thresholds.yaml").write_text(
        yaml.safe_dump(result.recommended_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print("\n============================================")
    print(" KJB Threshold Optimizer complete")
    print("============================================")
    print(f"Input : {range_file}")
    print(f"Output: {out_dir}")
    print("Recommended:")
    for key, value in result.recommended_params.items():
        print(f"  {key}: {value}")
    print(f"Details: {paths['top_configs']}")
    print("NOTE: recommendation is not applied to config/default.yaml automatically.")


if __name__ == "__main__":
    main()
