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
from optimization import DynamicThresholdAdapter  # noqa: E402


CLOSE_MFE_D20 = "close_MFE_D20"
CLOSE_MAE_D20 = "close_MAE_D20"
CLOSE_EXCURSION_RATIO_D20 = "close_excursion_ratio_D20"


def _latest_range_file() -> Path:
    files = list((BASE_DIR / "results").glob("range_*/dynamic_range_events.csv"))
    if not files:
        raise FileNotFoundError("No dynamic_range_events.csv found. Run run_dynamic_range.bat first.")
    return max(files, key=lambda p: p.stat().st_mtime)


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def add_close_path_excursions(df: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    """Add reproducible D+N close-path excursion metrics.

    Dynamic range files already contain direction-adjusted D+1..D+N close returns.
    We intentionally call these *close* MFE/MAE so they are not confused with true
    intraday high/low MFE/MAE. They are useful for threshold optimization without
    re-fetching market data and remain point-in-time reproducible from the range CSV.

    - close_MFE_D20: best direction-adjusted close return from D+1..D+20, floored at 0.
    - close_MAE_D20: worst direction-adjusted close return from D+1..D+20, capped at 0.
    - close_excursion_ratio_D20: MFE / max(|MAE|, 0.5%), clipped to [0, 10].

    The 0.5% denominator floor and ratio cap prevent nearly-zero MAE observations
    from dominating fold z-scores.
    """
    out = df.copy()
    cols = [f"D+{h}" for h in range(1, int(horizon) + 1)]
    missing = [c for c in cols if c not in out.columns]
    if missing:
        raise ValueError(
            "Dynamic optimizer requires D+1..D+20 path columns; missing: "
            + ", ".join(missing[:5])
            + (" ..." if len(missing) > 5 else "")
        )

    path = out[cols].apply(pd.to_numeric, errors="coerce")
    available = path.notna().any(axis=1)
    mfe = path.max(axis=1, skipna=True).clip(lower=0.0)
    mae = path.min(axis=1, skipna=True).clip(upper=0.0)
    mfe = mfe.where(available)
    mae = mae.where(available)

    denominator = mae.abs().clip(lower=0.005)
    ratio = (mfe / denominator).clip(lower=0.0, upper=10.0)
    ratio = ratio.where(available)

    suffix = int(horizon)
    out[f"close_MFE_D{suffix}"] = mfe
    out[f"close_MAE_D{suffix}"] = mae
    out[f"close_excursion_ratio_D{suffix}"] = ratio
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Dynamic V2.3 stage-aware purged walk-forward threshold optimizer")
    p.add_argument("--range-file")
    p.add_argument("--optimizer-config", default="threshold_optimizer.yaml")
    p.add_argument("--stage", type=int, choices=[1, 2, 3], default=3)
    p.add_argument("--current-confirmed-score", type=float, default=70.0)
    p.add_argument("--out")
    args = p.parse_args()

    range_file = _resolve(args.range_file, _latest_range_file())
    optimizer_cfg = yaml.safe_load(
        _resolve(args.optimizer_config, BASE_DIR / "threshold_optimizer.yaml").read_text(encoding="utf-8")
    ) or {}
    df = pd.read_csv(range_file, encoding="utf-8-sig", dtype={"ticker": str}, low_memory=False)
    df = add_close_path_excursions(df, horizon=20)

    print(f"[INFO] optimizer input: {range_file}")
    print(f"[INFO] Dynamic V2.3 target stage: {args.stage}")
    print(
        "[INFO] D+20 risk metrics: "
        f"{CLOSE_MAE_D20} / {CLOSE_MFE_D20} / {CLOSE_EXCURSION_RATIO_D20}"
    )
    print("[INFO] Excursions use D+1..D+20 direction-adjusted closes, not intraday high/low.")

    out_dir = _resolve(args.out, range_file.parent / "optimizer")
    stage_dir = out_dir / f"stage{args.stage}"

    adapter = DynamicThresholdAdapter(
        phase="confirmed",
        analyzer_config={"confirmed_score": float(args.current_confirmed_score), "target_stage": int(args.stage)},
    )
    result = ThresholdOptimizer(adapter, optimizer_cfg).run(df)
    paths = result.write(stage_dir / "confirmed")
    result.current_vs_optimized.to_csv(stage_dir / "current_vs_optimized.csv", index=False, encoding="utf-8-sig")

    eligible_path = stage_dir / "recommended_thresholds.yaml"
    provisional_path = stage_dir / "provisional_thresholds.yaml"
    eligible_payload = result.recommended_config if result.eligible_for_application else {}
    provisional_payload = {} if result.eligible_for_application else result.recommended_config
    eligible_path.write_text(yaml.safe_dump(eligible_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    provisional_path.write_text(yaml.safe_dump(provisional_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    print("\n============================================")
    print(" Dynamic V2.3 Stage Threshold Optimizer complete")
    print("============================================")
    print(f"Input        : {range_file}")
    print(f"Target stage : {args.stage}")
    print(f"Output       : {stage_dir}")
    print(f"Candidate    : {result.recommended_params}")
    print(f"Quality      : {result.recommendation_quality}")
    print(f"Application  : {'ELIGIBLE' if result.eligible_for_application else 'NOT ELIGIBLE'}")
    print(f"Summary      : {paths['recommendation_summary']}")
    print(f"Config       : {eligible_path if result.eligible_for_application else provisional_path}")
    print("Lecture RSI/MACD/Ichimoku and 1:2:7 are not optimized.")
    print("Only one Stage quality threshold is optimized per run.")


if __name__ == "__main__":
    main()
