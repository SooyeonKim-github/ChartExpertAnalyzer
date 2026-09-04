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
from config import DEFAULT_CONFIG  # noqa: E402
from optimization import MAThresholdAdapter  # noqa: E402


def _latest_range_file() -> Path:
    files = list((BASE_DIR / "results").glob("range_*/range_all_results.csv"))
    if not files:
        raise FileNotFoundError("No MA range_all_results.csv found. Run run_ma_range.bat first.")
    return max(files, key=lambda p: (p.parent.name, p.stat().st_mtime))


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="MA purged walk-forward threshold optimizer")
    p.add_argument("--range-file")
    p.add_argument("--optimizer-config", default="threshold_optimizer.yaml")
    p.add_argument("--phase", choices=["confirmed", "strong", "both"], default="both")
    p.add_argument("--out")
    args = p.parse_args()

    range_file = _resolve(args.range_file, _latest_range_file())
    optimizer_cfg = yaml.safe_load(
        _resolve(args.optimizer_config, BASE_DIR / "threshold_optimizer.yaml").read_text(encoding="utf-8")
    ) or {}
    analyzer_cfg = DEFAULT_CONFIG.to_dict()
    df = pd.read_csv(range_file, encoding="utf-8-sig", dtype={"Ticker": str})
    out_dir = _resolve(args.out, range_file.parent / "optimizer")
    out_dir.mkdir(parents=True, exist_ok=True)

    confirmed = None
    strong = None
    combined: dict = {}
    comparisons: list[pd.DataFrame] = []

    if args.phase in {"confirmed", "both"}:
        adapter = MAThresholdAdapter(phase="confirmed", analyzer_config=analyzer_cfg)
        confirmed = ThresholdOptimizer(adapter, optimizer_cfg).run(df)
        confirmed.write(out_dir / "confirmed")
        combined = _deep_merge(combined, confirmed.recommended_config)
        c = confirmed.current_vs_optimized.copy()
        c.insert(0, "phase", "confirmed")
        comparisons.append(c)

    if args.phase in {"strong", "both"}:
        floor = confirmed.recommended_params if confirmed is not None else None
        adapter = MAThresholdAdapter(
            phase="strong",
            analyzer_config=analyzer_cfg,
            confirmed_floor=floor,
        )
        strong = ThresholdOptimizer(adapter, optimizer_cfg).run(df)
        strong.write(out_dir / "strong")
        combined = _deep_merge(combined, strong.recommended_config)
        c = strong.current_vs_optimized.copy()
        c.insert(0, "phase", "strong")
        comparisons.append(c)

    if comparisons:
        pd.concat(comparisons, ignore_index=True).to_csv(
            out_dir / "current_vs_optimized.csv", index=False, encoding="utf-8-sig"
        )
    (out_dir / "recommended_thresholds.yaml").write_text(
        yaml.safe_dump(combined, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    print("\n============================================")
    print(" MA Threshold Optimizer complete")
    print("============================================")
    print(f"Input : {range_file}")
    print(f"Output: {out_dir}")
    if confirmed is not None:
        print(f"CONFIRMED: {confirmed.recommended_params}")
    if strong is not None:
        print(f"STRONG   : {strong.recommended_params}")
    print("NOTE: recommendation is not applied to config.py automatically.")


if __name__ == "__main__":
    main()
