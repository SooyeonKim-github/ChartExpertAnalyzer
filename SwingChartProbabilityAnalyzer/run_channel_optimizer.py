from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from config import DEFAULT_CONFIG
from optimization import SwingThresholdAdapter, SwingThresholdOptimizer
from run_threshold_optimizer import (
    _holdout_comparison,
    _load_optimizer_input,
    _resolve_optimizer_input,
    _resolve_path,
    _split_development_holdout,
)

BASE_DIR = Path(__file__).resolve().parent


def _validate_channel_only_config(cfg: dict) -> None:
    search = (cfg.get("search_space", {}) or {}).get("confirmed", {}) or {}
    scores = list(search.get("entry_score", []))
    channels = list(search.get("max_entry_channel_position", []))

    if scores != [90]:
        raise ValueError(
            "V2.3 must keep entry_score fixed at [90]. "
            f"Current config: {scores}"
        )
    if not channels:
        raise ValueError("V2.3 channel search space is empty")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Swing Threshold Optimizer V2.3: keep entry score at 90 and "
            "optimize max_entry_channel_position on development data only"
        )
    )
    parser.add_argument(
        "--range-file",
        help=(
            "Accepts a bare range folder name, range directory, threshold_input, "
            "manifest.csv, or range_all_results.csv."
        ),
    )
    parser.add_argument(
        "--optimizer-config",
        default="threshold_optimizer_channel_v2_3.yaml",
    )
    parser.add_argument("--out")
    args = parser.parse_args()

    input_path = _resolve_optimizer_input(args.range_file)
    config_path = _resolve_path(
        args.optimizer_config,
        BASE_DIR / "threshold_optimizer_channel_v2_3.yaml",
    )
    optimizer_cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    _validate_channel_only_config(optimizer_cfg)

    df, range_dir = _load_optimizer_input(input_path)
    development, reference_2026, split_info = _split_development_holdout(
        df, optimizer_cfg
    )

    print(f"[INFO] optimizer input       : {input_path}")
    print(f"[INFO] loaded rows           : {len(df):,}")
    print(
        f"[INFO] development          : {split_info['actual_development_start']} ~ "
        f"{split_info['actual_development_end']} ({len(development):,} rows)"
    )
    print(
        f"[INFO] boundary purge       : {split_info['purged_boundary_start']} ~ "
        f"{split_info['purged_boundary_end']} "
        f"({split_info['holdout_purge_trading_days']} trading days)"
    )
    print(
        f"[INFO] 2026 reference       : {split_info['actual_holdout_start']} ~ "
        f"{split_info['actual_holdout_end']} ({len(reference_2026):,} rows)"
    )
    print("[INFO] entry score fixed    : 90")

    out_dir = _resolve_path(args.out, range_dir / "optimizer_v2_3_channel")
    adapter = SwingThresholdAdapter(
        phase="confirmed",
        analyzer_config=DEFAULT_CONFIG.to_dict(),
    )
    optimizer = SwingThresholdOptimizer(adapter, optimizer_cfg)

    # Selection is development-only. 2026 never participates in grid ranking.
    result = optimizer.run(development)
    paths = result.write(out_dir / "development" / "confirmed")
    result.current_vs_optimized.to_csv(
        out_dir / "development_current_vs_optimized.csv",
        index=False,
        encoding="utf-8-sig",
    )

    candidate_path = out_dir / "recommended_thresholds.yaml"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        yaml.safe_dump(
            result.recommended_config,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    # 2026 has already been inspected in V2.2. Keep it reference-only and do not
    # use it to choose among V2.3 candidates.
    reference_comparison, reference_summary = _holdout_comparison(
        optimizer,
        adapter,
        reference_2026,
        result.recommended_params,
        optimizer_cfg,
    )
    reference_csv = out_dir / "reference_2026_comparison.csv"
    reference_comparison.to_csv(
        reference_csv,
        index=False,
        encoding="utf-8-sig",
    )

    summary_payload = {
        "version": "V2.3",
        "mode": "channel_only",
        "selection_basis": "development_only",
        "entry_score_fixed": 90,
        "channel_candidates": (
            optimizer_cfg.get("search_space", {})
            .get("confirmed", {})
            .get("max_entry_channel_position", [])
        ),
        "split": split_info,
        "walk_forward_recommendation_quality": result.recommendation_quality,
        "eligible_for_review": bool(result.eligible_for_application),
        "recommended_params": result.recommended_params,
        "reference_2026": reference_summary,
        "reference_2026_used_for_selection": False,
        "reference_2026_already_inspected_in_v2_2": True,
        "production_application_ready": False,
        "production_note": (
            "V2.3 selects channel only from 2021-2025 development walk-forward. "
            "2026 is reference-only because it was already inspected in V2.2."
        ),
    }
    summary_path = out_dir / "v2_3_summary.yaml"
    summary_path.write_text(
        yaml.safe_dump(summary_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print("\n============================================")
    print(" Swing Channel Optimizer V2.3 complete")
    print("============================================")
    print("Entry Score         : 90 (FIXED)")
    print(
        "Channel Grid        : "
        + str(
            optimizer_cfg.get("search_space", {})
            .get("confirmed", {})
            .get("max_entry_channel_position", [])
        )
    )
    print(f"Output              : {out_dir}")
    print(f"Candidate           : {result.recommended_params}")
    print(f"WF Quality          : {result.recommendation_quality}")
    print(f"Development Summary : {paths['recommendation_summary']}")
    print(f"Top Configs         : {paths['top_configs']}")
    print(f"Reference 2026      : {reference_csv}")
    print(f"V2.3 Summary        : {summary_path}")
    print(
        "NOTE: Select the channel from development walk-forward only. "
        "Do not re-rank candidates using the 2026 reference report."
    )


if __name__ == "__main__":
    main()
