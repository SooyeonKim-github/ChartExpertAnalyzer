from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
for p in (REPO_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ThresholdOptimization import ThresholdOptimizer  # noqa: E402
from config import DEFAULT_CONFIG  # noqa: E402
from optimization import SwingThresholdAdapter  # noqa: E402


def _latest_range_file() -> Path:
    files = list((BASE_DIR / "results").glob("range_*/range_all_results.csv"))
    if not files:
        raise FileNotFoundError("No Swing range_all_results.csv found. Run main_range.py first.")
    return max(files, key=lambda p: (p.parent.name, p.stat().st_mtime))


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def main() -> None:
    p = argparse.ArgumentParser(description="Swing purged walk-forward threshold optimizer")
    p.add_argument("--range-file")
    p.add_argument("--optimizer-config", default="threshold_optimizer.yaml")
    p.add_argument("--out")
    args = p.parse_args()

    range_file = _resolve(args.range_file, _latest_range_file())
    optimizer_cfg = yaml.safe_load(
        _resolve(args.optimizer_config, BASE_DIR / "threshold_optimizer.yaml").read_text(encoding="utf-8")
    ) or {}
    df = pd.read_csv(range_file, encoding="utf-8-sig", dtype={"Ticker": str})

    mfe = pd.to_numeric(df.get("MFE_20D_Pct"), errors="coerce")
    mae = pd.to_numeric(df.get("MAE_20D_Pct"), errors="coerce")
    denom = mae.abs().replace(0, np.nan)
    df["optimizer_excursion_ratio_D20"] = mfe / denom

    out_dir = _resolve(args.out, range_file.parent / "optimizer")
    adapter = SwingThresholdAdapter(
        phase="confirmed",
        analyzer_config=DEFAULT_CONFIG.to_dict(),
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
    print(" Swing Threshold Optimizer complete")
    print("============================================")
    print(f"Input : {range_file}")
    print(f"Output: {out_dir}")
    print(f"Recommended: {result.recommended_params}")
    print("NOTE: recommendation is not applied to config.py automatically.")


if __name__ == "__main__":
    main()
