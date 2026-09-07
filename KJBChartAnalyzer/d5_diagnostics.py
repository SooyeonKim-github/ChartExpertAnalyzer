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


def apply_overextension_penalty(
    events: pd.DataFrame,
    rs_soft: float = 85.0,
    rs_hard: float = 92.0,
    leader_soft: float = 80.0,
    leader_hard: float = 88.0,
    sector_soft: float = 78.0,
    sector_hard: float = 86.0,
    recent5_soft: float = 0.10,
    recent5_hard: float = 0.15,
) -> pd.DataFrame:
    """D+5용 과열 페널티를 별도 컬럼으로 계산한다.

    원래 selection/timing/status는 훼손하지 않는다. Threshold optimizer 전 단계에서
    기존 로직과 V2 후보 점수를 비교할 수 있도록 diagnostic score만 추가한다.
    """
    out = events.copy()
    rs = _num(out, "relative_strength_score")
    leader = _num(out, "leader_score")
    sector = _num(out, "sector_leader_score")
    recent5 = _num(out, "rs_rel_return_5d")
    selection = _num(out, "selection_score", 50.0).fillna(50.0)
    timing = _num(out, "timing_score", 50.0).fillna(50.0)

    penalty = pd.Series(0.0, index=out.index)
    reasons = [[] for _ in range(len(out))]

    def add_penalty(mask: pd.Series, points: float, label: str) -> None:
        nonlocal penalty
        mask = mask.fillna(False)
        penalty.loc[mask] += points
        for i in np.flatnonzero(mask.to_numpy()):
            reasons[i].append(label)

    add_penalty(rs.ge(rs_soft), 2.0, f"RS>={rs_soft:g}")
    add_penalty(rs.ge(rs_hard), 3.0, f"RS>={rs_hard:g}")
    add_penalty(leader.ge(leader_soft), 2.0, f"Leader>={leader_soft:g}")
    add_penalty(leader.ge(leader_hard), 3.0, f"Leader>={leader_hard:g}")
    add_penalty(sector.ge(sector_soft), 1.5, f"SectorLeader>={sector_soft:g}")
    add_penalty(sector.ge(sector_hard), 2.5, f"SectorLeader>={sector_hard:g}")
    add_penalty(recent5.ge(recent5_soft), 2.0, f"RS5D>={recent5_soft:.0%}")
    add_penalty(recent5.ge(recent5_hard), 3.0, f"RS5D>={recent5_hard:.0%}")

    # D+5에서는 장기 Selection보다 Timing을 조금 더 반영한다.
    base = selection * 0.45 + timing * 0.55
    out["overextension_penalty"] = penalty.round(2)
    out["overextension_reason"] = [" | ".join(x) for x in reasons]
    out["d5_base_score"] = base.round(2)
    out["d5_adjusted_score"] = (base - penalty).clip(0, 100).round(2)
    out["d5_overextended"] = penalty.ge(5.0)

    if "signal_date" in out.columns:
        out["d5_daily_rank"] = out.groupby("signal_date")["d5_adjusted_score"].rank(
            method="first", ascending=False
        ).astype("Int64")
    return out


def _perf(frame: pd.DataFrame, label: str, group_type: str, group_value: str) -> dict:
    d5 = pd.to_numeric(frame.get("D+5"), errors="coerce").dropna()
    excess = pd.to_numeric(frame.get("D+5_excess"), errors="coerce").dropna() if "D+5_excess" in frame.columns else pd.Series(dtype=float)
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

    # Status
    if "Status" in events.columns:
        for value, g in events.groupby("Status", dropna=False):
            rows.append(_perf(g, f"Status={value}", "status", value))

    # 연속 점수 구간
    score_cols = [
        "selection_score", "technical_score", "timing_score", "relative_strength_score",
        "leader_score", "sector_leader_score", "d5_base_score", "d5_adjusted_score",
        "overextension_penalty",
    ]
    for col in score_cols:
        if col not in events.columns:
            continue
        s = pd.to_numeric(events[col], errors="coerce")
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

    if "breadth_above_ma20_ratio" in events.columns:
        b = pd.to_numeric(events["breadth_above_ma20_ratio"], errors="coerce")
        bucket = pd.cut(b, [-np.inf, .3, .5, .7, np.inf], labels=["<30%", "30~50%", "50~70%", "70%+"])
        for value in bucket.cat.categories:
            g = events[bucket == value]
            if not g.empty:
                rows.append(_perf(g, f"breadth_ma20={value}", "breadth_ma20", value))

    return pd.DataFrame(rows)


def _topn_summary(events: pd.DataFrame) -> pd.DataFrame:
    if "d5_daily_rank" not in events.columns:
        return pd.DataFrame()
    rows = []
    for n in [3, 5, 10, 20]:
        g = events[pd.to_numeric(events["d5_daily_rank"], errors="coerce") <= n]
        rows.append(_perf(g, f"Daily Top {n}", "daily_topn", n))
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="KJB D+5 diagnostics + overextension penalty")
    p.add_argument("--range-dir", default=None, help="results/range_YYYYMMDD_YYYYMMDD 경로. 생략 시 최신 range 자동 선택")
    p.add_argument("--events", default=None, help="chart_range_events.csv 직접 지정")
    p.add_argument("--rs-soft", type=float, default=85.0)
    p.add_argument("--rs-hard", type=float, default=92.0)
    p.add_argument("--leader-soft", type=float, default=80.0)
    p.add_argument("--leader-hard", type=float, default=88.0)
    p.add_argument("--sector-soft", type=float, default=78.0)
    p.add_argument("--sector-hard", type=float, default=86.0)
    p.add_argument("--recent5-soft", type=float, default=0.10)
    p.add_argument("--recent5-hard", type=float, default=0.15)
    args = p.parse_args()

    if args.events:
        events_path = Path(args.events)
        range_dir = events_path.resolve().parent
    else:
        range_dir = Path(args.range_dir) if args.range_dir else _latest_range_dir(RESULTS_ROOT)
        events_path = range_dir / "chart_range_events.csv"

    if not events_path.exists():
        raise FileNotFoundError(events_path)

    events = pd.read_csv(events_path, low_memory=False)
    if "signal_date" in events.columns:
        events["signal_date"] = pd.to_datetime(events["signal_date"], errors="coerce").dt.normalize()

    # Market regime / breadth 결합
    regime_path = range_dir / "market_regime_daily.csv"
    if regime_path.exists() and "signal_date" in events.columns and "market" in events.columns:
        regime = pd.read_csv(regime_path, low_memory=False)
        if "date" in regime.columns:
            regime["date"] = pd.to_datetime(regime["date"], errors="coerce").dt.normalize()
            keep = [c for c in [
                "date", "market", "market_regime", "breadth_above_ma20_ratio",
                "breadth_above_ma60_ratio", "breadth_positive_5d_ratio", "breadth_positive_20d_ratio",
            ] if c in regime.columns]
            if keep:
                events = events.drop(columns=[c for c in keep if c not in {"date", "market"} and c in events.columns], errors="ignore")
                events = events.merge(regime[keep].rename(columns={"date": "signal_date"}), on=["signal_date", "market"], how="left")
        bench = _build_benchmark_d5(regime)
        if not bench.empty:
            events = events.merge(bench, on=["signal_date", "market"], how="left")
            if "D+5" in events.columns:
                events["D+5_excess"] = pd.to_numeric(events["D+5"], errors="coerce") - pd.to_numeric(events["benchmark_D+5"], errors="coerce")

    out = apply_overextension_penalty(
        events,
        rs_soft=args.rs_soft, rs_hard=args.rs_hard,
        leader_soft=args.leader_soft, leader_hard=args.leader_hard,
        sector_soft=args.sector_soft, sector_hard=args.sector_hard,
        recent5_soft=args.recent5_soft, recent5_hard=args.recent5_hard,
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
    print("KJB D+5 Diagnostics + OverextensionPenalty")
    print("=" * 78)
    print("Input :", events_path)
    print("Rows  :", len(out))
    print()
    print("[Overextension D+5]")
    view = over[["group_value", "valid_d5", "avg_D+5", "median_D+5", "win_rate_D+5", "avg_excess_D+5"]].copy()
    for c in ["avg_D+5", "median_D+5", "win_rate_D+5", "avg_excess_D+5"]:
        view[c] = view[c].map(fmt)
    print(view.to_string(index=False))
    print()
    print("[Adjusted Score Daily Top N]")
    view = topn[["group_value", "valid_d5", "avg_D+5", "median_D+5", "win_rate_D+5", "avg_excess_D+5"]].copy()
    for c in ["avg_D+5", "median_D+5", "win_rate_D+5", "avg_excess_D+5"]:
        view[c] = view[c].map(fmt)
    print(view.to_string(index=False))
    print()
    print("[완료]")
    print("D+5 events      :", out_path)
    print("Diagnostics      :", diag_path)
    print("Top-N summary    :", topn_path)
    print("Overextension    :", over_path)


if __name__ == "__main__":
    main()
