from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ThresholdOptimization import ThresholdOptimizer  # noqa: E402
from leader_stock_analyzer import load_config  # noqa: E402
from leader_stock_analyzer.optimization import LeaderThresholdAdapter  # noqa: E402


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _latest_range_file() -> Path:
    candidates = list((BASE_DIR / "results").glob("range_*/range_all_results.csv"))
    if not candidates:
        raise FileNotFoundError(
            "No LeaderStockAnalyzer range_all_results.csv found. Run run_range.bat first."
        )
    return max(candidates, key=lambda p: (p.parent.name, p.stat().st_mtime))


def _resolve_path(value: str | None, default: Path | None = None) -> Path:
    if value is None:
        if default is None:
            raise ValueError("path is required")
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def _run_phase(
    phase: str,
    df: pd.DataFrame,
    analyzer_cfg: dict,
    optimizer_cfg: dict,
    out_dir: Path,
    *,
    confirmed_floor: dict | None = None,
):
    adapter = LeaderThresholdAdapter(
        phase=phase,
        analyzer_config=analyzer_cfg,
        confirmed_floor=confirmed_floor,
    )
    optimizer = ThresholdOptimizer(adapter, optimizer_cfg)
    result = optimizer.run(df)
    paths = result.write(out_dir / phase)
    print(f"\n[{phase.upper()}] recommended")
    for key, value in result.recommended_params.items():
        print(f"  {key}: {value}")
    print(f"  -> {paths['recommended_thresholds']}")
    return result


def main() -> None:
    p = argparse.ArgumentParser(
        description="LeaderStockAnalyzer purged walk-forward threshold optimizer"
    )
    p.add_argument("--range-file", help="range_all_results.csv; default=latest range result")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--optimizer-config", default="config/threshold_optimizer.yaml")
    p.add_argument("--phase", choices=["confirmed", "strong", "both"], default="both")
    p.add_argument("--out", help="output folder; default=<range folder>/optimizer")
    args = p.parse_args()

    range_file = _resolve_path(args.range_file, _latest_range_file())
    analyzer_cfg = load_config(_resolve_path(args.config))
    optimizer_cfg = yaml.safe_load(
        _resolve_path(args.optimizer_config).read_text(encoding="utf-8")
    ) or {}

    if not range_file.exists():
        raise FileNotFoundError(range_file)
    df = pd.read_csv(
        range_file,
        encoding="utf-8-sig",
        dtype={"scan_date": str, "ticker": str},
    )
    out_dir = _resolve_path(args.out, range_file.parent / "optimizer")
    out_dir.mkdir(parents=True, exist_ok=True)

    confirmed_result = None
    strong_result = None
    if args.phase in {"confirmed", "both"}:
        confirmed_result = _run_phase(
            "confirmed", df, analyzer_cfg, optimizer_cfg, out_dir
        )

    if args.phase in {"strong", "both"}:
        floor = confirmed_result.recommended_params if confirmed_result is not None else None
        strong_result = _run_phase(
            "strong",
            df,
            analyzer_cfg,
            optimizer_cfg,
            out_dir,
            confirmed_floor=floor,
        )

    combined: dict = {}
    summary_rows: list[pd.DataFrame] = []
    if confirmed_result is not None:
        combined = _deep_merge(combined, confirmed_result.recommended_config)
        tmp = confirmed_result.current_vs_optimized.copy()
        tmp.insert(0, "phase", "confirmed")
        summary_rows.append(tmp)
    if strong_result is not None:
        combined = _deep_merge(combined, strong_result.recommended_config)
        tmp = strong_result.current_vs_optimized.copy()
        tmp.insert(0, "phase", "strong")
        summary_rows.append(tmp)

    combined_path = out_dir / "recommended_thresholds.yaml"
    combined_path.write_text(
        yaml.safe_dump(combined, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    if summary_rows:
        pd.concat(summary_rows, ignore_index=True).to_csv(
            out_dir / "current_vs_optimized.csv",
            index=False,
            encoding="utf-8-sig",
        )

    print("\n============================================")
    print(" Threshold Optimizer complete")
    print("============================================")
    print(f"Input : {range_file}")
    print(f"Output: {out_dir}")
    print(f"Recommended config: {combined_path}")
    print("NOTE: recommended_thresholds.yaml is NOT applied to default.yaml automatically.")


if __name__ == "__main__":
    main()
