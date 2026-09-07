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
from chartsel.config import load_config  # noqa: E402
from optimization import KJBThresholdAdapter  # noqa: E402


D5_PATH_COLUMNS = [f"D+{h}" for h in range(1, 6)]


def _latest_range_file() -> Path:
    files = list((BASE_DIR / "results").glob("range_*/chart_range_events.csv"))
    if not files:
        raise FileNotFoundError("No KJB chart_range_events.csv found. Run the KJB range backtest first.")
    return max(files, key=lambda p: p.stat().st_mtime)


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def _ensure_d5_path_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Build complete D+5 close-path quality metrics for old/new Range files."""
    missing = [c for c in D5_PATH_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"D+5 optimizer requires forward-return columns: {missing}")

    out = df.copy()
    path = out[D5_PATH_COLUMNS].apply(pd.to_numeric, errors="coerce")
    complete = path.notna().all(axis=1)

    if "MFE_D5" not in out.columns:
        out["MFE_D5"] = path.max(axis=1).where(complete)
    else:
        out["MFE_D5"] = pd.to_numeric(out["MFE_D5"], errors="coerce").where(complete)

    if "MAE_D5" not in out.columns:
        out["MAE_D5"] = path.min(axis=1).where(complete)
    else:
        out["MAE_D5"] = pd.to_numeric(out["MAE_D5"], errors="coerce").where(complete)

    if "excursion_ratio_D5" not in out.columns:
        mfe = pd.to_numeric(out["MFE_D5"], errors="coerce")
        mae = pd.to_numeric(out["MAE_D5"], errors="coerce")
        denom = mfe.abs() + mae.abs()
        ratio = pd.Series(np.nan, index=out.index, dtype=float)
        valid = complete & denom.gt(1e-12)
        ratio.loc[valid] = mfe.loc[valid] / denom.loc[valid]
        ratio.loc[complete & ~denom.gt(1e-12)] = 0.0
        out["excursion_ratio_D5"] = ratio
    else:
        out["excursion_ratio_D5"] = pd.to_numeric(
            out["excursion_ratio_D5"], errors="coerce"
        ).where(complete)

    return out


def main() -> None:
    p = argparse.ArgumentParser(description="KJB D+5 purged walk-forward threshold optimizer")
    p.add_argument("--range-file")
    # D+5 optimizer는 live default가 아니라 실험용 d5 config를 기본으로 사용한다.
    p.add_argument("--config", default="config/d5_diagnostics.yaml")
    p.add_argument("--optimizer-config", default="config/threshold_optimizer.yaml")
    p.add_argument("--out")
    args = p.parse_args()

    range_file = _resolve(args.range_file, _latest_range_file())
    cfg = load_config(str(_resolve(args.config, BASE_DIR / "config/d5_diagnostics.yaml")))
    optimizer_cfg = yaml.safe_load(
        _resolve(args.optimizer_config, BASE_DIR / "config/threshold_optimizer.yaml").read_text(encoding="utf-8")
    ) or {}

    df = pd.read_csv(range_file, encoding="utf-8-sig", dtype={"ticker": str})
    print(f"[INFO] optimizer input: {range_file}")
    df = _ensure_d5_path_metrics(df)
    out_dir = _resolve(args.out, range_file.parent / "optimizer_d5")

    adapter = KJBThresholdAdapter(phase="confirmed", analyzer_config=cfg)
    result = ThresholdOptimizer(adapter, optimizer_cfg).run(df)
    paths = result.write(out_dir / "confirmed")
    result.current_vs_optimized.to_csv(out_dir / "current_vs_optimized.csv", index=False, encoding="utf-8-sig")
    (out_dir / "recommended_thresholds.yaml").write_text(
        yaml.safe_dump(result.recommended_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print("\n============================================")
    print(" KJB D+5 Threshold Optimizer complete")
    print("============================================")
    print(f"Input : {range_file}")
    print(f"Output: {out_dir}")
    print("Target: D+5")
    print("Score : D5 score (Selection - OverextensionPenalty)")
    print("Path metrics: MFE_D5 / MAE_D5 / excursion_ratio_D5 (D+1..D+5 close path)")
    print("Recommended:")
    for key, value in result.recommended_params.items():
        print(f"  {key}: {value}")
    print(f"Details: {paths['top_configs']}")
    print("NOTE: recommendation is not applied to config/default.yaml automatically.")


if __name__ == "__main__":
    main()
