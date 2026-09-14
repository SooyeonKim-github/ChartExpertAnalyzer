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
from run_threshold_optimizer import (  # noqa: E402
    _load_optimizer_input,
    _resolve_optimizer_input,
    _split_development_holdout,
)


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def _load_recommended_params(path: Path) -> dict[str, float]:
    if not path.exists():
        raise FileNotFoundError(
            f"Recommended threshold config not found: {path}\n"
            "Run run_optimize_thresholds.bat (V2.1) first."
        )

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entry_score = payload.get("entry_score", payload.get("strong_confirmed_score"))
    channel = payload.get("max_entry_channel_position")
    if entry_score is None or channel is None:
        raise ValueError(
            f"Recommended threshold config is empty or invalid: {path}"
        )

    return {
        "entry_score": float(entry_score),
        "max_entry_channel_position": float(channel),
    }


def _parse_extra_channels(value: str) -> list[float]:
    values: list[float] = []
    for token in str(value).split(","):
        token = token.strip()
        if not token:
            continue
        channel = float(token)
        if not 0.0 <= channel <= 1.0:
            raise ValueError(f"Invalid channel position: {channel}")
        values.append(channel)
    return values


def _candidate_label(prefix: str, channel: float) -> str:
    return f"{prefix}_{channel:.2f}".replace(".", "_")


def _build_candidates(
    current: dict[str, float],
    recommended: dict[str, float],
    extra_channels: list[float],
) -> list[tuple[str, dict[str, float]]]:
    candidates: list[tuple[str, dict[str, float]]] = [
        ("CURRENT", dict(current)),
        (
            "SCORE_ONLY",
            {
                "entry_score": float(recommended["entry_score"]),
                "max_entry_channel_position": float(
                    current["max_entry_channel_position"]
                ),
            },
        ),
        (
            "CHANNEL_ONLY_RECOMMENDED",
            {
                "entry_score": float(current["entry_score"]),
                "max_entry_channel_position": float(
                    recommended["max_entry_channel_position"]
                ),
            },
        ),
    ]

    for channel in extra_channels:
        params = {
            "entry_score": float(current["entry_score"]),
            "max_entry_channel_position": float(channel),
        }
        # Keep the report compact if an extra channel is already represented.
        if any(
            abs(float(p["entry_score"]) - params["entry_score"]) < 1e-12
            and abs(
                float(p["max_entry_channel_position"])
                - params["max_entry_channel_position"]
            )
            < 1e-12
            for _, p in candidates
        ):
            continue
        candidates.append((_candidate_label("CHANNEL_ONLY", channel), params))

    candidates.append(("FULL_OPTIMIZED", dict(recommended)))
    return candidates


def _evaluate_ablation(
    optimizer: SwingThresholdOptimizer,
    adapter: SwingThresholdAdapter,
    holdout: pd.DataFrame,
    candidates: list[tuple[str, dict[str, float]]],
    optimizer_cfg: dict,
) -> tuple[pd.DataFrame, dict]:
    ecfg = optimizer_cfg.get("evaluation", {}) or {}
    min_samples = int(ecfg.get("holdout_min_samples", 30))
    min_unique_dates = int(ecfg.get("holdout_min_unique_dates", 15))

    rows: list[dict] = []
    for name, params in candidates:
        metrics = optimizer.evaluate_parameters(holdout, params)
        sample_valid = (
            int(metrics.get("count") or 0) >= min_samples
            and int(metrics.get("unique_dates") or 0) >= min_unique_dates
        )
        rows.append(
            {
                "candidate": name,
                "entry_score": float(params["entry_score"]),
                "max_entry_channel_position": float(
                    params["max_entry_channel_position"]
                ),
                **metrics,
                "holdout_sample_valid": bool(sample_valid),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("No ablation candidate was evaluated")

    current_row = frame.loc[frame["candidate"] == "CURRENT"].iloc[0]
    for metric in optimizer.aggregate_metric_names:
        if metric not in frame.columns:
            continue
        current_value = current_row.get(metric)
        if pd.isna(current_value):
            continue
        numeric = pd.to_numeric(frame[metric], errors="coerce")
        frame[f"delta_vs_current_{metric}"] = numeric - float(current_value)

    summary = {
        "diagnostic_only": True,
        "holdout_min_samples": min_samples,
        "holdout_min_unique_dates": min_unique_dates,
        "candidates": [
            {"name": name, **params} for name, params in candidates
        ],
        "note": (
            "Ablation uses the already-isolated 2026 final holdout only to explain "
            "score/channel effects. Do not select a new production threshold from "
            "this report; doing so would turn the holdout into training data."
        ),
    }
    return frame, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Swing Threshold V2.2 diagnostic ablation on the isolated 2026 holdout"
        )
    )
    parser.add_argument(
        "--range-file",
        help=(
            "Accepts a bare range folder name, range directory, threshold_input, "
            "manifest.csv, or range_all_results.csv."
        ),
    )
    parser.add_argument("--optimizer-config", default="threshold_optimizer.yaml")
    parser.add_argument(
        "--recommended-config",
        help=(
            "V2.1 recommended_thresholds.yaml. Default: the selected range's "
            "optimizer_v2_1/recommended_thresholds.yaml"
        ),
    )
    parser.add_argument(
        "--extra-channel",
        default="0.50",
        help="Extra current-score channel-only diagnostics, comma separated.",
    )
    parser.add_argument("--out")
    args = parser.parse_args()

    input_path = _resolve_optimizer_input(args.range_file)
    df, range_dir = _load_optimizer_input(input_path)

    optimizer_cfg_path = _resolve_path(
        args.optimizer_config, BASE_DIR / "threshold_optimizer.yaml"
    )
    optimizer_cfg = yaml.safe_load(
        optimizer_cfg_path.read_text(encoding="utf-8")
    ) or {}

    _, holdout, split_info = _split_development_holdout(df, optimizer_cfg)

    recommended_path = _resolve_path(
        args.recommended_config,
        range_dir / "optimizer_v2_1" / "recommended_thresholds.yaml",
    )
    recommended = _load_recommended_params(recommended_path)

    adapter = SwingThresholdAdapter(
        phase="confirmed",
        analyzer_config=DEFAULT_CONFIG.to_dict(),
    )
    optimizer = SwingThresholdOptimizer(adapter, optimizer_cfg)
    current = adapter.current_parameters()
    extra_channels = _parse_extra_channels(args.extra_channel)
    candidates = _build_candidates(current, recommended, extra_channels)

    report, summary = _evaluate_ablation(
        optimizer,
        adapter,
        holdout,
        candidates,
        optimizer_cfg,
    )

    out_dir = _resolve_path(args.out, range_dir / "optimizer_v2_2_ablation")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "final_holdout_ablation.csv"
    yaml_path = out_dir / "final_holdout_ablation_summary.yaml"

    report.to_csv(csv_path, index=False, encoding="utf-8-sig")
    summary_payload = {
        "split": split_info,
        "recommended_config_source": str(recommended_path),
        "current_parameters": current,
        "recommended_parameters": recommended,
        **summary,
    }
    yaml_path.write_text(
        yaml.safe_dump(summary_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    display_columns = [
        "candidate",
        "entry_score",
        "max_entry_channel_position",
        "count",
        "d10_median_return",
        "d20_median_return",
        "d20_win_rate",
        "hit_mid_rate",
        "hit_prior_high_rate",
        "stop_hit_rate",
        "median_mfe20",
        "median_mae20",
        "median_excursion_ratio",
    ]
    existing = [c for c in display_columns if c in report.columns]

    print("\n============================================")
    print(" Swing Threshold Ablation V2.2 complete")
    print("============================================")
    print(f"Input              : {input_path}")
    print(f"Recommended config : {recommended_path}")
    print(
        f"Final holdout      : {split_info['actual_holdout_start']} ~ "
        f"{split_info['actual_holdout_end']}"
    )
    print("\n[2026 Holdout Ablation]")
    print(report[existing].to_string(index=False))
    print(f"\nAblation CSV       : {csv_path}")
    print(f"Ablation Summary   : {yaml_path}")
    print(
        "NOTE: This is diagnostic-only. Do not choose a new threshold from the "
        "2026 holdout ablation itself."
    )


if __name__ == "__main__":
    main()
