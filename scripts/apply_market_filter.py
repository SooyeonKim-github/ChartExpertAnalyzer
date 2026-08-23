from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MILESTONES = (5, 10, 20, 40, 60)

DEFAULTS = {
    "healthy_ma20": 0.60,
    "healthy_ma60": 0.50,
    "riskoff_ma20": 0.30,
    "riskoff_ma60": 0.25,
    "shock_drawdown": -0.08,
    "shock_rebound_5d": 0.02,
    "shock_down_5d": -0.02,
}


def _num(value) -> float:
    try:
        x = float(value)
        return x if np.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _ticker(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _normalize_market(value) -> str:
    text = str(value or "").strip().upper()
    if "KOSDAQ" in text or text in {"KQ", "^KQ11", "2001"}:
        return "KOSDAQ"
    if "KOSPI" in text or text in {"KS", "^KS11", "1001"}:
        return "KOSPI"
    return ""


def _market_state(
    row: pd.Series,
    daily_top_n: int,
    cfg: dict[str, float],
) -> tuple[str, int, str]:
    regime = str(row.get("market_regime", "unknown") or "unknown").lower()
    b20 = _num(row.get("breadth_above_ma20_ratio"))
    b60 = _num(row.get("breadth_above_ma60_ratio"))
    ret5 = _num(row.get("index_return_5d"))
    dd20 = _num(row.get("index_drawdown_20d"))

    if np.isfinite(dd20) and dd20 <= cfg["shock_drawdown"]:
        if np.isfinite(ret5) and ret5 >= cfg["shock_rebound_5d"]:
            return (
                "SHOCK_REBOUND",
                min(3, daily_top_n),
                "large drawdown + 5D rebound; keep top candidates without source-consensus rule",
            )
        if np.isfinite(ret5) and ret5 <= cfg["shock_down_5d"]:
            return (
                "RISK_OFF",
                min(1, daily_top_n),
                "large drawdown still falling; reduce new entries",
            )

    if (
        np.isfinite(b20)
        and np.isfinite(b60)
        and b20 < cfg["riskoff_ma20"]
        and b60 < cfg["riskoff_ma60"]
    ):
        return (
            "RISK_OFF",
            min(1, daily_top_n),
            "very weak breadth; reduce new entries",
        )

    if regime == "downtrend":
        return "RISK_OFF", min(1, daily_top_n), "downtrend; reduce new entries"

    if regime == "volatile":
        if (
            np.isfinite(dd20)
            and dd20 <= -0.05
            and np.isfinite(ret5)
            and ret5 > 0
        ):
            return (
                "SHOCK_REBOUND",
                min(3, daily_top_n),
                "volatile drawdown + positive 5D rebound",
            )
        return "SELECTIVE", min(3, daily_top_n), "volatile; reduce number of new entries"

    if regime == "uptrend":
        if (
            np.isfinite(b20)
            and np.isfinite(b60)
            and b20 >= cfg["healthy_ma20"]
            and b60 >= cfg["healthy_ma60"]
        ):
            return (
                "HEALTHY",
                daily_top_n,
                "uptrend + healthy breadth; original TOP N allowed",
            )
        return (
            "SELECTIVE",
            min(3, daily_top_n),
            "uptrend but breadth not healthy; reduce number of new entries",
        )

    if regime == "range":
        return "SELECTIVE", min(3, daily_top_n), "range; reduce number of new entries"

    return (
        "SELECTIVE",
        min(3, daily_top_n),
        "unknown/other context; conservative position-count reduction",
    )


def _build_daily_context(
    context: pd.DataFrame,
    daily_top_n: int,
    cfg: dict[str, float],
) -> pd.DataFrame:
    x = context.copy()
    x["signal_date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["market"] = x["market"].map(_normalize_market)
    if "market_regime" in x.columns:
        x["market_regime"] = x["market_regime"].fillna("unknown").astype(str).str.lower()
    else:
        x["market_regime"] = "unknown"
    x = x.dropna(subset=["signal_date"])
    x = x[x["market"].ne("")].drop_duplicates(["signal_date", "market"], keep="last")

    states = x.apply(lambda r: _market_state(r, daily_top_n, cfg), axis=1)
    x["market_filter_state"] = [s[0] for s in states]
    x["market_filter_max_positions"] = [s[1] for s in states]
    x["market_filter_reason"] = [s[2] for s in states]
    return x.sort_values(["signal_date", "market"]).reset_index(drop=True)


def _apply_filter(
    top: pd.DataFrame,
    daily_context: pd.DataFrame,
    daily_top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    x = top.copy()
    x["signal_date"] = pd.to_datetime(x["signal_date"], errors="coerce").dt.normalize()
    x["ticker"] = x["ticker"].map(_ticker)
    x["market"] = x["market"].map(_normalize_market)

    context_cols = [
        "signal_date",
        "market",
        "market_regime",
        "index_close",
        "index_return_5d",
        "index_return_20d",
        "index_drawdown_20d",
        "index_ma20_gap",
        "index_ma60_gap",
        "index_volatility_20d",
        "index_volatility_120d",
        "breadth_stock_count",
        "breadth_valid_ma20",
        "breadth_valid_ma60",
        "breadth_above_ma20_ratio",
        "breadth_above_ma60_ratio",
        "breadth_positive_5d_ratio",
        "breadth_positive_20d_ratio",
        "market_filter_state",
        "market_filter_max_positions",
        "market_filter_reason",
    ]
    context_cols = [c for c in context_cols if c in daily_context.columns]

    replace_cols = [
        c
        for c in context_cols
        if c not in {"signal_date", "market"} and c in x.columns
    ]
    if replace_cols:
        x = x.drop(columns=replace_cols)
    x = x.merge(
        daily_context[context_cols],
        on=["signal_date", "market"],
        how="left",
    )

    x["market_filter_state"] = x["market_filter_state"].fillna("SELECTIVE")
    x["market_filter_max_positions"] = pd.to_numeric(
        x["market_filter_max_positions"], errors="coerce"
    ).fillna(min(3, daily_top_n)).astype(int)
    x["market_filter_reason"] = x["market_filter_reason"].fillna(
        "missing market context; conservative position-count reduction"
    )

    x["market_filter_rank"] = np.nan
    selected_idx: list[int] = []

    for (_, _), grp in x.groupby(["signal_date", "market"], sort=False):
        ranked = grp.sort_values(
            ["combined_score", "ticker"],
            ascending=[False, True],
        )
        cap = int(ranked["market_filter_max_positions"].iloc[0]) if len(ranked) else 0
        ranked = ranked.head(max(0, cap))
        for rank, idx in enumerate(ranked.index, 1):
            x.loc[idx, "market_filter_rank"] = rank
            selected_idx.append(idx)

    x["market_filter_selected"] = x.index.isin(selected_idx)

    selected = x[x["market_filter_selected"]].copy()
    if not selected.empty:
        selected = selected.sort_values(
            ["signal_date", "combined_score", "ticker"],
            ascending=[True, False, True],
        )
        selected["market_filter_global_rank"] = (
            selected.groupby("signal_date").cumcount() + 1
        )
        keep = selected[
            selected["market_filter_global_rank"] <= daily_top_n
        ].index
        x["market_filter_selected"] = x.index.isin(keep)
        selected = x[x["market_filter_selected"]].copy()
        selected = selected.sort_values(
            ["signal_date", "combined_score", "ticker"],
            ascending=[True, False, True],
        )
        selected["market_filter_global_rank"] = (
            selected.groupby("signal_date").cumcount() + 1
        )

    decisions = x.sort_values(
        ["signal_date", "combined_score", "ticker"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    selected = selected.reset_index(drop=True)
    return decisions, selected


def _event_summary(cohorts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict] = []
    for cohort, frame in cohorts.items():
        for h in MILESTONES:
            col = f"ret_D{h}"
            v = (
                pd.to_numeric(frame[col], errors="coerce").dropna()
                if col in frame.columns
                else pd.Series(dtype=float)
            )
            rows.append({
                "cohort": cohort,
                "horizon": h,
                "signal_count": int(len(frame)),
                "valid_count": int(len(v)),
                "avg_return": float(v.mean()) if len(v) else np.nan,
                "median_return": float(v.median()) if len(v) else np.nan,
                "win_rate": float((v > 0).mean()) if len(v) else np.nan,
                "p25_return": float(v.quantile(0.25)) if len(v) else np.nan,
                "p75_return": float(v.quantile(0.75)) if len(v) else np.nan,
            })
    return pd.DataFrame(rows)


def _date_summary(cohorts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict] = []
    for cohort, frame in cohorts.items():
        for h in MILESTONES:
            col = f"ret_D{h}"
            basket = (
                frame.groupby("signal_date")[col].mean().dropna()
                if (not frame.empty and col in frame.columns)
                else pd.Series(dtype=float)
            )
            rows.append({
                "cohort": cohort,
                "horizon": h,
                "date_count": int(len(basket)),
                "avg_basket_return": float(basket.mean()) if len(basket) else np.nan,
                "median_basket_return": float(basket.median()) if len(basket) else np.nan,
                "positive_date_rate": float((basket > 0).mean()) if len(basket) else np.nan,
            })
    return pd.DataFrame(rows)


def _write_summary(
    path: Path,
    event: pd.DataFrame,
    date: pd.DataFrame,
    daily: pd.DataFrame,
    daily_top_n: int,
    cfg: dict[str, float],
) -> None:
    lines = [
        "# Market Filter Backtest",
        "",
        "Analyzer 출처 간 합의 여부는 사용하지 않고, 기존 COMBINED_TOP 후보의 순서와 시장 상태만 사용해 신규진입 수를 제한한다.",
        "",
        "## Filter Rules",
        "",
        f"- HEALTHY: uptrend + breadth(MA20>={cfg['healthy_ma20']:.0%}, MA60>={cfg['healthy_ma60']:.0%}) -> 기존 TOP{daily_top_n} 허용",
        "- SELECTIVE: range/volatile/약한 breadth -> 기존 TOP 후보 중 최대 3개",
        f"- SHOCK_REBOUND: 20D drawdown<={cfg['shock_drawdown']:.0%} + 5D rebound>={cfg['shock_rebound_5d']:.0%} -> 기존 TOP 후보 중 최대 3개",
        "- RISK_OFF: downtrend/급락 지속/극단적 weak breadth -> 기존 TOP 후보 중 최대 1개",
        "- Analyzer 동시 포착 여부에 따른 우대/제외 규칙은 없다.",
        "- Combined Score 자체에는 시장 가감점을 넣지 않는다.",
        "",
        "## Performance",
        "",
        "| Cohort | D+5 | D+10 | D+20 |",
        "|---|---:|---:|---:|",
    ]
    for cohort in [f"COMBINED_TOP{daily_top_n}", "MARKET_FILTERED"]:
        vals = []
        for h in (5, 10, 20):
            row = event[
                (event["cohort"] == cohort) & (event["horizon"] == h)
            ]
            if row.empty or pd.isna(row.iloc[0]["avg_return"]):
                vals.append("-")
            else:
                r = row.iloc[0]
                vals.append(
                    f"{r['avg_return']*100:.2f}% / win {r['win_rate']*100:.1f}%"
                )
        lines.append(f"| {cohort} | {vals[0]} | {vals[1]} | {vals[2]} |")

    lines.extend(["", "## Market State Days", ""])
    if not daily.empty:
        counts = (
            daily.groupby("market_filter_state")["signal_date"]
            .nunique()
            .sort_values(ascending=False)
        )
        for state, count in counts.items():
            lines.append(f"- {state}: {int(count)} market-days")

    lines.extend([
        "",
        "## Caution",
        "",
        "- 이 임계값은 초기 검증값이며 최적화된 값이 아니다. 여러 기간 holdout에서 반복 검증해야 한다.",
        "- Breadth는 해당 Range 실행의 Universe(TOP N) 내부 비율이므로 과거 실제 Universe 복원 문제는 그대로 남는다.",
        "- 같은 종목의 연속 신호는 독립 표본이 아니므로 Event와 Date-equal 결과를 함께 본다.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Apply market filter to Combined TOP N without analyzer-consensus rule"
    )
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--daily-top-n", type=int, default=5)
    p.add_argument("--output-root", default=str(ROOT / "results"))
    p.add_argument("--healthy-ma20", type=float, default=DEFAULTS["healthy_ma20"])
    p.add_argument("--healthy-ma60", type=float, default=DEFAULTS["healthy_ma60"])
    p.add_argument("--riskoff-ma20", type=float, default=DEFAULTS["riskoff_ma20"])
    p.add_argument("--riskoff-ma60", type=float, default=DEFAULTS["riskoff_ma60"])
    p.add_argument("--shock-drawdown", type=float, default=DEFAULTS["shock_drawdown"])
    p.add_argument("--shock-rebound-5d", type=float, default=DEFAULTS["shock_rebound_5d"])
    p.add_argument("--shock-down-5d", type=float, default=DEFAULTS["shock_down_5d"])
    args = p.parse_args()

    start, end = args.date_range.replace(" ", "").split("~", 1)
    range_key = f"{start}_{end}"
    combined_dir = Path(args.output_root) / f"combined_range_{range_key}"
    kjb_dir = ROOT / "KJBChartAnalyzer" / "results" / f"range_{range_key}"
    top_path = combined_dir / f"combined_daily_top{args.daily_top_n}.csv"
    context_path = kjb_dir / "market_regime_daily.csv"

    if not top_path.exists():
        raise FileNotFoundError(f"Combined TOP file not found: {top_path}")
    if not context_path.exists():
        raise FileNotFoundError(f"Market context file not found: {context_path}")

    cfg = {
        "healthy_ma20": args.healthy_ma20,
        "healthy_ma60": args.healthy_ma60,
        "riskoff_ma20": args.riskoff_ma20,
        "riskoff_ma60": args.riskoff_ma60,
        "shock_drawdown": args.shock_drawdown,
        "shock_rebound_5d": args.shock_rebound_5d,
        "shock_down_5d": args.shock_down_5d,
    }

    top = pd.read_csv(
        top_path,
        encoding="utf-8-sig",
        dtype={"ticker": str},
    )
    top["ticker"] = top["ticker"].map(_ticker)
    context = pd.read_csv(context_path, encoding="utf-8-sig")
    daily = _build_daily_context(context, args.daily_top_n, cfg)
    decisions, selected = _apply_filter(top, daily, args.daily_top_n)

    cohorts = {
        f"COMBINED_TOP{args.daily_top_n}": top,
        "MARKET_FILTERED": selected,
    }
    event = _event_summary(cohorts)
    date = _date_summary(cohorts)

    decisions.to_csv(
        combined_dir / "market_filter_decisions.csv",
        index=False,
        encoding="utf-8-sig",
    )
    selected.to_csv(
        combined_dir / "market_filtered_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    daily.to_csv(
        combined_dir / "market_filter_daily.csv",
        index=False,
        encoding="utf-8-sig",
    )
    event.to_csv(
        combined_dir / "performance_market_filter_event.csv",
        index=False,
        encoding="utf-8-sig",
    )
    date.to_csv(
        combined_dir / "performance_market_filter_date_equal.csv",
        index=False,
        encoding="utf-8-sig",
    )

    summary_path = combined_dir / "market_filter_summary.md"
    _write_summary(
        summary_path,
        event,
        date,
        daily,
        args.daily_top_n,
        cfg,
    )

    xlsx = combined_dir / "combined_range_backtest.xlsx"
    if xlsx.exists():
        try:
            with pd.ExcelWriter(
                xlsx,
                engine="openpyxl",
                mode="a",
                if_sheet_exists="replace",
            ) as writer:
                decisions.to_excel(writer, sheet_name="market_filter_decisions", index=False)
                selected.to_excel(writer, sheet_name="market_filtered", index=False)
                daily.to_excel(writer, sheet_name="market_filter_daily", index=False)
                event.to_excel(writer, sheet_name="market_filter_event", index=False)
                date.to_excel(writer, sheet_name="market_filter_date", index=False)
        except Exception as exc:
            print(f"[WARN] Excel market-filter sheets skipped: {exc}")

    print("\n[MARKET FILTER - NO ANALYZER CONSENSUS RULE]")
    print("원본 Combined TOP은 변경하지 않았습니다.")
    print("Filtered:", combined_dir / "market_filtered_candidates.csv")
    print("Decisions:", combined_dir / "market_filter_decisions.csv")
    print("Summary :", summary_path)

    view = event[event["horizon"].isin([5, 10, 20])].copy()
    if not view.empty:
        view["avg_return"] = view["avg_return"].map(
            lambda v: "-" if pd.isna(v) else f"{v*100:.2f}%"
        )
        view["win_rate"] = view["win_rate"].map(
            lambda v: "-" if pd.isna(v) else f"{v*100:.1f}%"
        )
        print(
            view[["cohort", "horizon", "valid_count", "avg_return", "win_rate"]]
            .to_string(index=False)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
