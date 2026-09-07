from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RESULTS_ROOT = ROOT / "results"


def _latest_range_dir(root: Path) -> Path:
    dirs = sorted(
        [p for p in root.glob("range_*") if p.is_dir() and (p / "chart_range_events.csv").exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not dirs:
        raise FileNotFoundError(f"range 결과를 찾지 못했습니다: {root}")
    return dirs[0]


def _num(frame: pd.DataFrame, col: str, default=np.nan) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[col], errors="coerce")


def _build_benchmark_d5(regime: pd.DataFrame) -> pd.DataFrame:
    if regime.empty or not {"date", "market", "index_close"}.issubset(regime.columns):
        return pd.DataFrame(columns=["signal_date", "market", "benchmark_D+5"])
    x = regime.copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["index_close"] = pd.to_numeric(x["index_close"], errors="coerce")
    x = x.dropna(subset=["date", "market", "index_close"]).sort_values(["market", "date"])
    x["benchmark_D+5"] = x.groupby("market")["index_close"].shift(-5) / x["index_close"] - 1.0
    return x[["date", "market", "benchmark_D+5"]].rename(columns={"date": "signal_date"})


def load_events_with_market_context(range_dir: Path, events_path: Path | None = None) -> pd.DataFrame:
    events_path = events_path or (range_dir / "chart_range_events.csv")
    events = pd.read_csv(events_path, low_memory=False)
    if "signal_date" in events.columns:
        events["signal_date"] = pd.to_datetime(events["signal_date"], errors="coerce").dt.normalize()

    regime_path = range_dir / "market_regime_daily.csv"
    if regime_path.exists() and {"signal_date", "market"}.issubset(events.columns):
        regime = pd.read_csv(regime_path, low_memory=False)
        if "date" in regime.columns:
            regime["date"] = pd.to_datetime(regime["date"], errors="coerce").dt.normalize()
            keep = [c for c in [
                "date", "market", "market_regime", "breadth_above_ma20_ratio",
                "breadth_above_ma60_ratio", "breadth_positive_5d_ratio", "breadth_positive_20d_ratio",
            ] if c in regime.columns]
            if keep:
                drop_cols = [c for c in keep if c not in {"date", "market"} and c in events.columns]
                events = events.drop(columns=drop_cols, errors="ignore")
                events = events.merge(
                    regime[keep].rename(columns={"date": "signal_date"}),
                    on=["signal_date", "market"], how="left",
                )
        bench = _build_benchmark_d5(regime)
        if not bench.empty:
            events = events.drop(columns=["benchmark_D+5", "D+5_excess"], errors="ignore")
            events = events.merge(bench, on=["signal_date", "market"], how="left")
            if "D+5" in events.columns:
                events["D+5_excess"] = _num(events, "D+5") - _num(events, "benchmark_D+5")
    return events


def apply_overextension_penalty(
    events: pd.DataFrame,
    *,
    selection_weight: float = 0.45,
    timing_weight: float = 0.55,
    rs_hard: float = 92.0,
    leader_soft: float = 80.0,
    leader_hard: float = 88.0,
    sector_soft: float = 78.0,
    sector_hard: float = 86.0,
    leader_soft_penalty: float = 2.0,
    leader_hard_penalty: float = 2.0,
    sector_soft_penalty: float = 1.5,
    sector_hard_penalty: float = 1.5,
    rs_leader_combo_penalty: float = 3.0,
    triple_combo_penalty: float = 4.0,
    overextension_threshold: float = 8.0,
) -> pd.DataFrame:
    """KJB D+5 V2 score/과열 페널티를 계산한다.

    백테스트 결과상 RS 고점 단독은 반드시 나쁘지 않았으므로 단독 RS 페널티는 제거하고,
    Leader/Sector Leader 과열과 RS+Leader, RS+Leader+Sector의 복합 과열에 집중한다.
    기존 selection_score/Status는 변경하지 않는다.
    """
    out = events.copy()
    sw = float(selection_weight)
    tw = float(timing_weight)
    total_w = sw + tw
    if total_w <= 0:
        raise ValueError("selection_weight + timing_weight must be > 0")
    sw, tw = sw / total_w, tw / total_w

    selection = _num(out, "selection_score", 50.0).fillna(50.0)
    timing = _num(out, "timing_score", 50.0).fillna(50.0)
    rs = _num(out, "relative_strength_score")
    leader = _num(out, "leader_score")
    sector = _num(out, "sector_leader_score")

    penalty = pd.Series(0.0, index=out.index)
    reasons = [[] for _ in range(len(out))]

    def add(mask: pd.Series, points: float, label: str) -> None:
        nonlocal penalty
        mask = mask.fillna(False)
        penalty.loc[mask] += float(points)
        for i in np.flatnonzero(mask.to_numpy()):
            reasons[i].append(label)

    leader_soft_mask = leader.ge(leader_soft)
    leader_hard_mask = leader.ge(leader_hard)
    sector_soft_mask = sector.ge(sector_soft)
    sector_hard_mask = sector.ge(sector_hard)
    rs_hard_mask = rs.ge(rs_hard)

    add(leader_soft_mask, leader_soft_penalty, f"Leader>={leader_soft:g}")
    add(leader_hard_mask, leader_hard_penalty, f"Leader>={leader_hard:g}")
    add(sector_soft_mask, sector_soft_penalty, f"SectorLeader>={sector_soft:g}")
    add(sector_hard_mask, sector_hard_penalty, f"SectorLeader>={sector_hard:g}")
    add(rs_hard_mask & leader_soft_mask, rs_leader_combo_penalty, f"RS>={rs_hard:g}+Leader")
    add(rs_hard_mask & leader_soft_mask & sector_soft_mask, triple_combo_penalty, "RS+Leader+Sector")

    base = selection * sw + timing * tw
    out["overextension_penalty"] = penalty.round(2)
    out["overextension_reason"] = [" | ".join(x) for x in reasons]
    out["d5_base_score"] = base.round(2)
    out["d5_adjusted_score"] = (base - penalty).clip(0, 100).round(2)
    out["d5_overextended"] = penalty.ge(float(overextension_threshold))
    out["d5_selection_weight"] = round(sw, 4)
    out["d5_timing_weight"] = round(tw, 4)

    if "signal_date" in out.columns:
        out["d5_daily_rank"] = out.groupby("signal_date")["d5_adjusted_score"].rank(
            method="first", ascending=False
        ).astype("Int64")
    return out


def apply_d5_status(
    events: pd.DataFrame,
    *,
    selection_min: float = 70.0,
    timing_min: float = 72.0,
    d5_score_min: float = 70.0,
    overextension_max_exclusive: float = 8.0,
) -> pd.DataFrame:
    """기존 Status를 보존하면서 D+5 전용 D5_Status를 병렬 생성한다.

    WATCH를 CONFIRMED로 승격하지 않는다. 기존 CONFIRMED 중 D+5 조건을 통과한 종목만
    D5_CONFIRMED가 되고, 탈락한 기존 CONFIRMED는 D5_WATCH로 내려간다.
    """
    out = events.copy()
    base_status = out.get("Status", pd.Series("WATCH", index=out.index)).astype(str)
    selection = _num(out, "selection_score")
    timing = _num(out, "timing_score")
    d5_score = _num(out, "d5_adjusted_score")
    penalty = _num(out, "overextension_penalty", 0.0).fillna(0.0)

    d5_confirmed = (
        base_status.eq("CONFIRMED")
        & selection.ge(float(selection_min))
        & timing.ge(float(timing_min))
        & d5_score.ge(float(d5_score_min))
        & penalty.lt(float(overextension_max_exclusive))
    )
    d5_rejected = base_status.eq("REJECTED")
    out["D5_Status"] = np.select(
        [d5_confirmed, d5_rejected],
        ["D5_CONFIRMED", "D5_REJECTED"],
        default="D5_WATCH",
    )
    out["D5_Status_reason"] = np.where(
        d5_confirmed,
        "baseline CONFIRMED + D5 thresholds passed",
        np.where(
            d5_rejected,
            "baseline REJECTED",
            "baseline WATCH or D5 threshold/overextension failed",
        ),
    )
    if "signal_date" in out.columns:
        out["d5_confirmed_daily_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        mask = out["D5_Status"].eq("D5_CONFIRMED")
        if mask.any():
            ranks = out.loc[mask].groupby("signal_date")["d5_adjusted_score"].rank(
                method="first", ascending=False
            ).astype("Int64")
            out.loc[mask, "d5_confirmed_daily_rank"] = ranks
    return out


def build_d5_strategy(
    events: pd.DataFrame,
    *,
    selection_weight: float = 0.45,
    timing_weight: float = 0.55,
    rs_hard: float = 92.0,
    leader_soft: float = 80.0,
    leader_hard: float = 88.0,
    sector_soft: float = 78.0,
    sector_hard: float = 86.0,
    rs_leader_combo_penalty: float = 3.0,
    triple_combo_penalty: float = 4.0,
    overextension_max_exclusive: float = 8.0,
    selection_min: float = 70.0,
    timing_min: float = 72.0,
    d5_score_min: float = 70.0,
) -> pd.DataFrame:
    out = apply_overextension_penalty(
        events,
        selection_weight=selection_weight,
        timing_weight=timing_weight,
        rs_hard=rs_hard,
        leader_soft=leader_soft,
        leader_hard=leader_hard,
        sector_soft=sector_soft,
        sector_hard=sector_hard,
        rs_leader_combo_penalty=rs_leader_combo_penalty,
        triple_combo_penalty=triple_combo_penalty,
        overextension_threshold=overextension_max_exclusive,
    )
    return apply_d5_status(
        out,
        selection_min=selection_min,
        timing_min=timing_min,
        d5_score_min=d5_score_min,
        overextension_max_exclusive=overextension_max_exclusive,
    )


def _perf(frame: pd.DataFrame, label: str, group_type: str, group_value: str) -> dict:
    d5 = _num(frame, "D+5").dropna()
    excess = _num(frame, "D+5_excess").dropna() if "D+5_excess" in frame.columns else pd.Series(dtype=float)
    return {
        "group_type": group_type,
        "group_value": str(group_value),
        "label": label,
        "count": int(len(frame)),
        "valid_d5": int(d5.size),
        "avg_D+5": float(d5.mean()) if len(d5) else np.nan,
        "median_D+5": float(d5.median()) if len(d5) else np.nan,
        "win_rate_D+5": float((d5 > 0).mean()) if len(d5) else np.nan,
        "avg_excess_D+5": float(excess.mean()) if len(excess) else np.nan,
        "median_excess_D+5": float(excess.median()) if len(excess) else np.nan,
        "excess_win_rate_D+5": float((excess > 0).mean()) if len(excess) else np.nan,
    }


def _bucket_diagnostics(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for status_col in ["Status", "D5_Status"]:
        if status_col in events.columns:
            for value, g in events.groupby(status_col, dropna=False):
                rows.append(_perf(g, f"{status_col}={value}", status_col, value))

    score_cols = [
        "selection_score", "technical_score", "timing_score", "relative_strength_score",
        "leader_score", "sector_leader_score", "d5_base_score", "d5_adjusted_score",
        "overextension_penalty",
    ]
    for col in score_cols:
        if col not in events.columns:
            continue
        s = _num(events, col)
        if col == "overextension_penalty":
            bins = [-0.01, 0, 2, 5, 8, 12, np.inf]
            labels = ["0", "0~2", "2~5", "5~8", "8~12", "12+"]
        else:
            bins = [-np.inf, 50, 60, 70, 75, 80, 85, 90, np.inf]
            labels = ["<50", "50~60", "60~70", "70~75", "75~80", "80~85", "85~90", "90+"]
        bucket = pd.cut(s, bins=bins, labels=labels, right=False)
        for value in labels:
            g = events[bucket == value]
            if not g.empty:
                rows.append(_perf(g, f"{col}={value}", col, value))

    if "market_regime" in events.columns:
        for value, g in events.groupby("market_regime", dropna=False):
            rows.append(_perf(g, f"market_regime={value}", "market_regime", value))
    return pd.DataFrame(rows)


def _topn_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rank_col, prefix in [("d5_daily_rank", "ALL"), ("d5_confirmed_daily_rank", "D5_CONFIRMED")]:
        if rank_col not in events.columns:
            continue
        rank = _num(events, rank_col)
        for n in [1, 3, 5, 10, 20]:
            g = events[rank.le(n)]
            rows.append(_perf(g, f"{prefix} Daily Top {n}", f"{prefix.lower()}_daily_topn", n))
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="KJB D+5 V2 diagnostics")
    p.add_argument("--range-dir", default=None)
    p.add_argument("--events", default=None)
    p.add_argument("--selection-weight", type=float, default=0.45)
    p.add_argument("--timing-weight", type=float, default=0.55)
    p.add_argument("--rs-hard", type=float, default=92.0)
    p.add_argument("--leader-soft", type=float, default=80.0)
    p.add_argument("--leader-hard", type=float, default=88.0)
    p.add_argument("--sector-soft", type=float, default=78.0)
    p.add_argument("--sector-hard", type=float, default=86.0)
    p.add_argument("--combo-rs-leader", type=float, default=3.0)
    p.add_argument("--combo-triple", type=float, default=4.0)
    p.add_argument("--overextension-max", type=float, default=8.0)
    p.add_argument("--selection-min", type=float, default=70.0)
    p.add_argument("--timing-min", type=float, default=72.0)
    p.add_argument("--d5-score-min", type=float, default=70.0)
    args = p.parse_args()

    if args.events:
        events_path = Path(args.events)
        range_dir = events_path.resolve().parent
    else:
        range_dir = Path(args.range_dir) if args.range_dir else _latest_range_dir(RESULTS_ROOT)
        events_path = range_dir / "chart_range_events.csv"
    if not events_path.exists():
        raise FileNotFoundError(events_path)

    events = load_events_with_market_context(range_dir, events_path)
    out = build_d5_strategy(
        events,
        selection_weight=args.selection_weight,
        timing_weight=args.timing_weight,
        rs_hard=args.rs_hard,
        leader_soft=args.leader_soft,
        leader_hard=args.leader_hard,
        sector_soft=args.sector_soft,
        sector_hard=args.sector_hard,
        rs_leader_combo_penalty=args.combo_rs_leader,
        triple_combo_penalty=args.combo_triple,
        overextension_max_exclusive=args.overextension_max,
        selection_min=args.selection_min,
        timing_min=args.timing_min,
        d5_score_min=args.d5_score_min,
    )

    diagnostics = _bucket_diagnostics(out)
    topn = _topn_summary(out)
    over = pd.concat([
        pd.DataFrame([_perf(out[~out["d5_overextended"]], "Not overextended", "overextension", "normal")]),
        pd.DataFrame([_perf(out[out["d5_overextended"]], "Overextended", "overextension", "overextended")]),
    ], ignore_index=True)

    out_path = range_dir / "chart_range_events_d5.csv"
    diag_path = range_dir / "kjb_d5_diagnostics.csv"
    topn_path = range_dir / "kjb_d5_topn_summary.csv"
    over_path = range_dir / "kjb_d5_overextension_summary.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    diagnostics.to_csv(diag_path, index=False, encoding="utf-8-sig")
    topn.to_csv(topn_path, index=False, encoding="utf-8-sig")
    over.to_csv(over_path, index=False, encoding="utf-8-sig")

    def fmt(v):
        return "-" if pd.isna(v) else f"{v*100:.2f}%"

    print("=" * 78)
    print("KJB D+5 V2 Diagnostics")
    print("=" * 78)
    print("Input :", events_path)
    print("Rows  :", len(out))
    print("D5 Status counts:")
    print(out["D5_Status"].value_counts().to_string())
    print("\n[Overextension D+5]")
    view = over[["group_value", "valid_d5", "avg_D+5", "median_D+5", "win_rate_D+5", "avg_excess_D+5"]].copy()
    for c in ["avg_D+5", "median_D+5", "win_rate_D+5", "avg_excess_D+5"]:
        view[c] = view[c].map(fmt)
    print(view.to_string(index=False))
    print("\n[D5 Adjusted Daily Top N]")
    view = topn[["label", "valid_d5", "avg_D+5", "median_D+5", "win_rate_D+5", "avg_excess_D+5"]].copy()
    for c in ["avg_D+5", "median_D+5", "win_rate_D+5", "avg_excess_D+5"]:
        view[c] = view[c].map(fmt)
    print(view.to_string(index=False))
    print("\n[완료]")
    print("D+5 events      :", out_path)
    print("Diagnostics      :", diag_path)
    print("Top-N summary    :", topn_path)
    print("Overextension    :", over_path)


if __name__ == "__main__":
    main()
