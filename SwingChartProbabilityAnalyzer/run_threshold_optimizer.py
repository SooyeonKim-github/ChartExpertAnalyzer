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

from config import DEFAULT_CONFIG  # noqa: E402
from optimization import SwingThresholdAdapter, SwingThresholdOptimizer  # noqa: E402


def _latest_optimizer_input() -> Path:
    manifests = list(
        (BASE_DIR / "results").glob("range_*/threshold_input/manifest.csv")
    )
    if manifests:
        return max(manifests, key=lambda p: p.stat().st_mtime)

    files = list((BASE_DIR / "results").glob("range_*/range_all_results.csv"))
    if not files:
        raise FileNotFoundError(
            "No Swing threshold_input/manifest.csv or range_all_results.csv found. "
            "Run the range analyzer / threshold exporter first."
        )
    return max(files, key=lambda p: p.stat().st_mtime)


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def _resolve_optimizer_input(value: str | None) -> Path:
    """Resolve convenient user input forms.

    Accepted examples:
      - Enter / None -> latest threshold_input manifest
      - range_20210101_20260901 -> results/range_20210101_20260901
      - results/range_20210101_20260901
      - threshold_input directory / manifest.csv / full CSV
      - absolute path
    """
    if not value:
        return _latest_optimizer_input()

    raw = Path(value)
    if raw.is_absolute():
        return raw

    direct = BASE_DIR / raw
    if direct.exists():
        return direct

    under_results = BASE_DIR / "results" / raw
    if under_results.exists():
        return under_results

    # Preserve a useful path in the eventual error message even if nothing exists.
    if raw.name.startswith("range_") and len(raw.parts) == 1:
        return under_results
    return direct


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        encoding="utf-8-sig",
        dtype={"Ticker": str},
        low_memory=False,
    )


def _load_manifest(manifest_path: Path) -> pd.DataFrame:
    manifest = _read_csv(manifest_path)
    if "file" not in manifest.columns:
        raise ValueError(f"manifest missing 'file' column: {manifest_path}")

    parts: list[pd.DataFrame] = []
    for name in manifest["file"].dropna().astype(str):
        part_path = manifest_path.parent / name
        if not part_path.exists():
            raise FileNotFoundError(f"threshold shard not found: {part_path}")
        parts.append(_read_csv(part_path))

    if not parts:
        raise ValueError(f"threshold manifest contains no data parts: {manifest_path}")
    return pd.concat(parts, ignore_index=True, sort=False)


def _load_optimizer_input(path: Path) -> tuple[pd.DataFrame, Path]:
    """Load either exported threshold shards or a legacy full range CSV.

    Returns (dataframe, range_dir). range_dir is used for optimizer outputs.
    """
    path = path.resolve()

    if path.is_dir():
        if path.name == "threshold_input":
            manifest = path / "manifest.csv"
            if not manifest.exists():
                raise FileNotFoundError(f"manifest not found: {manifest}")
            return _load_manifest(manifest), path.parent

        threshold_manifest = path / "threshold_input" / "manifest.csv"
        if threshold_manifest.exists():
            return _load_manifest(threshold_manifest), path

        full_range = path / "range_all_results.csv"
        if full_range.exists():
            return _read_csv(full_range), path

        raise FileNotFoundError(
            f"No threshold_input/manifest.csv or range_all_results.csv under: {path}"
        )

    if not path.exists():
        raise FileNotFoundError(
            f"Optimizer input not found: {path}\n"
            "Tip: enter only a range folder name such as range_20210101_20260901, "
            "or press Enter to use the latest exported threshold_input."
        )

    if path.name == "manifest.csv" and path.parent.name == "threshold_input":
        return _load_manifest(path), path.parent.parent

    if path.name.startswith("threshold_input_part_") and path.suffix.lower() == ".csv":
        return _read_csv(path), path.parent.parent

    if path.suffix.lower() == ".csv":
        return _read_csv(path), path.parent

    raise ValueError(f"Unsupported optimizer input: {path}")


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "Swing 2D threshold optimizer: entry_score x max_entry_channel_position "
            "with purged long-horizon walk-forward validation"
        )
    )
    p.add_argument(
        "--range-file",
        help=(
            "Legacy name kept for compatibility. Accepts a bare range folder name, "
            "range_all_results.csv, range directory, threshold_input directory, or manifest.csv."
        ),
    )
    p.add_argument("--optimizer-config", default="threshold_optimizer.yaml")
    p.add_argument("--out")
    args = p.parse_args()

    input_path = _resolve_optimizer_input(args.range_file)
    optimizer_cfg = yaml.safe_load(
        _resolve_path(
            args.optimizer_config, BASE_DIR / "threshold_optimizer.yaml"
        ).read_text(encoding="utf-8")
    ) or {}

    df, range_dir = _load_optimizer_input(input_path)
    print(f"[INFO] optimizer input: {input_path}")
    print(f"[INFO] loaded rows   : {len(df):,}")
    if "Actual_Date" in df.columns:
        dates = pd.to_datetime(df["Actual_Date"], errors="coerce").dropna()
        if not dates.empty:
            print(
                f"[INFO] date range     : {dates.min().date()} ~ {dates.max().date()}"
            )

    out_dir = _resolve_path(args.out, range_dir / "optimizer_v2")
    adapter = SwingThresholdAdapter(
        phase="confirmed",
        analyzer_config=DEFAULT_CONFIG.to_dict(),
    )
    result = SwingThresholdOptimizer(adapter, optimizer_cfg).run(df)
    paths = result.write(out_dir / "confirmed")
    result.current_vs_optimized.to_csv(
        out_dir / "current_vs_optimized.csv",
        index=False,
        encoding="utf-8-sig",
    )

    eligible_path = out_dir / "recommended_thresholds.yaml"
    provisional_path = out_dir / "provisional_thresholds.yaml"
    if result.eligible_for_application:
        eligible_payload = result.recommended_config
        provisional_payload = {}
    else:
        eligible_payload = {}
        provisional_payload = result.recommended_config

    eligible_path.write_text(
        yaml.safe_dump(eligible_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    provisional_path.write_text(
        yaml.safe_dump(provisional_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print("\n============================================")
    print(" Swing Threshold Optimizer V2 complete")
    print("============================================")
    print(f"Input        : {input_path}")
    print(f"Output       : {out_dir}")
    print(f"Candidate    : {result.recommended_params}")
    print(f"Quality      : {result.recommendation_quality}")
    print(
        f"Application  : {'ELIGIBLE' if result.eligible_for_application else 'NOT ELIGIBLE'}"
    )
    print(f"Summary      : {paths['recommendation_summary']}")
    print(f"Comparison   : {out_dir / 'current_vs_optimized.csv'}")
    print(f"Top configs  : {paths['top_configs']}")
    print(f"Stability    : {paths['stability_report']}")
    if result.eligible_for_application:
        print(f"Eligible config: {eligible_path}")
    else:
        print(f"Provisional only: {provisional_path}")
    print(
        "NOTE: ACCEPTABLE/ROBUST means the walk-forward threshold is eligible "
        "for holdout review, not automatic production application."
    )


if __name__ == "__main__":
    main()
