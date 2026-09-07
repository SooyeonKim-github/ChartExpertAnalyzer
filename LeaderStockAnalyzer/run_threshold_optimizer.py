from __future__ import annotations

import argparse
import sys
from copy import deepcopy
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
    # Use the file that was actually generated/updated most recently. Sorting by
    # range folder name first can incorrectly prefer a newer single-day range
    # over a freshly generated long range.
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _resolve_path(value: str | None, default: Path | None = None) -> Path:
    if value is None:
        if default is None:
            raise ValueError("path is required")
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def _parse_scan_dates(df: pd.DataFrame) -> pd.Series:
    raw = df.get("scan_date", pd.Series(index=df.index, dtype=str)).astype(str).str.strip()
    ymd = pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
    fallback = pd.to_datetime(raw, errors="coerce")
    return ymd.fillna(fallback).dt.normalize()


def _print_input_summary(range_file: Path, df: pd.DataFrame) -> None:
    dates = _parse_scan_dates(df).dropna()
    unique = dates.drop_duplicates().sort_values()
    print("\n[INFO] Threshold optimizer input")
    print(f"  file         : {range_file}")
    print(f"  rows         : {len(df):,}")
    print(f"  trading days : {len(unique):,}")
    if not unique.empty:
        print(f"  date range   : {unique.iloc[0].date()} ~ {unique.iloc[-1].date()}")


def _write_strong_insufficient_diagnostics(
    df: pd.DataFrame,
    out_dir: Path,
    error: Exception,
) -> Path:
    """Persist useful diagnostics instead of losing a successful CONFIRMED run."""
    strong_dir = out_dir / "strong"
    strong_dir.mkdir(parents=True, exist_ok=True)

    work = df.copy()
    work["_scan_date"] = _parse_scan_dates(work)
    work["_d20_valid"] = pd.to_numeric(work.get("D+20"), errors="coerce").notna()
    status = work.get("status", pd.Series(index=work.index, dtype=str)).astype(str)
    work["_current_strong"] = status.eq("STRONG_CONFIRMED")
    work["month"] = work["_scan_date"].dt.to_period("M").astype(str)

    rows = []
    for month, grp in work[work["_scan_date"].notna()].groupby("month", sort=True):
        strong = grp[grp["_current_strong"]]
        rows.append(
            {
                "month": month,
                "trading_days": int(grp["_scan_date"].nunique()),
                "current_strong_count": int(len(strong)),
                "current_strong_D20_valid": int(strong["_d20_valid"].sum()),
                "current_strong_unique_dates_D20": int(
                    strong.loc[strong["_d20_valid"], "_scan_date"].nunique()
                ),
            }
        )

    diag_path = strong_dir / "insufficient_sample_diagnostics.csv"
    pd.DataFrame(rows).to_csv(diag_path, index=False, encoding="utf-8-sig")

    current_strong = work[work["_current_strong"]]
    current_valid = current_strong[current_strong["_d20_valid"]]
    note = (
        "STRONG threshold optimization was skipped because no parameter combination "
        "passed the configured out-of-sample sample requirements.\n\n"
        f"Reason: {error}\n\n"
        f"Current STRONG rows: {len(current_strong):,}\n"
        f"Current STRONG rows with valid D+20: {len(current_valid):,}\n"
        f"Current STRONG unique dates with valid D+20: "
        f"{current_valid['_scan_date'].nunique():,}\n\n"
        "CONFIRMED optimization remains valid and its recommendation is preserved.\n"
        "Do not relax STRONG sample constraints merely to force a result. "
        "Prefer a longer historical range (ideally multiple market regimes).\n"
    )
    (strong_dir / "INSUFFICIENT_SAMPLE.txt").write_text(note, encoding="utf-8")
    return diag_path


def _run_phase(
    phase: str,
    df: pd.DataFrame,
    analyzer_cfg: dict,
    optimizer_cfg: dict,
    out_dir: Path,
    *,
    confirmed_floor: dict | None = None,
):
    phase_cfg = deepcopy(optimizer_cfg)
    # LeaderStockAnalyzer currently uses one shared max_confirmed_chase_risk for
    # CONFIRMED and STRONG_CONFIRMED. In a two-phase run, keep that threshold
    # identical instead of producing contradictory recommendations.
    if phase == "strong" and confirmed_floor is not None:
        strong_space = phase_cfg.setdefault("search_space", {}).setdefault("strong", {})
        strong_space["max_chase_risk"] = [float(confirmed_floor["max_chase_risk"])]

    adapter = LeaderThresholdAdapter(
        phase=phase,
        analyzer_config=analyzer_cfg,
        confirmed_floor=confirmed_floor,
    )
    optimizer = ThresholdOptimizer(adapter, phase_cfg)
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
    p.add_argument("--range-file", help="range_all_results.csv; default=latest modified range result")
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
        low_memory=False,
    )
    _print_input_summary(range_file, df)
    out_dir = _resolve_path(args.out, range_file.parent / "optimizer")
    out_dir.mkdir(parents=True, exist_ok=True)

    confirmed_result = None
    strong_result = None
    strong_skip_error: Exception | None = None

    if args.phase in {"confirmed", "both"}:
        confirmed_result = _run_phase(
            "confirmed", df, analyzer_cfg, optimizer_cfg, out_dir
        )

    if args.phase in {"strong", "both"}:
        floor = confirmed_result.recommended_params if confirmed_result is not None else None
        try:
            strong_result = _run_phase(
                "strong",
                df,
                analyzer_cfg,
                optimizer_cfg,
                out_dir,
                confirmed_floor=floor,
            )
        except ValueError as exc:
            if args.phase == "strong":
                raise
            strong_skip_error = exc
            diag = _write_strong_insufficient_diagnostics(df, out_dir, exc)
            print("\n[STRONG] optimization skipped: insufficient out-of-sample sample")
            print(f"  reason     : {exc}")
            print(f"  diagnostics: {diag}")
            print("  action     : keep current STRONG thresholds; use a longer Range before optimizing STRONG")

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
    if strong_skip_error is not None:
        print("STRONG: skipped because OOS sample was insufficient; current STRONG thresholds were not replaced.")
    print("NOTE: recommended_thresholds.yaml is NOT applied to default.yaml automatically.")


if __name__ == "__main__":
    main()
