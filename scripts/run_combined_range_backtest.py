from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MILESTONES = (5, 10, 20, 40, 60)


def _ticker(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _num(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _normalize_market(value) -> str:
    text = str(value or "").strip().upper()
    if "KOSDAQ" in text or text in {"KQ", "^KQ11", "2001"}:
        return "KOSDAQ"
    if "KOSPI" in text or text in {"KS", "^KS11", "1001"}:
        return "KOSPI"
    return ""


def _text_col(df: pd.DataFrame, name: str, default: str = "") -> pd.Series:
    if name in df.columns:
        return df[name].fillna(default).astype(str)
    return pd.Series(default, index=df.index, dtype=str)


def _read_swing(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    out = pd.DataFrame(index=df.index)
    out["signal_date"] = pd.to_datetime(df["Actual_Date"], errors="coerce").dt.normalize()
    out["ticker"] = df["Ticker"].map(_ticker)
    out["name_swing"] = _text_col(df, "Name")
    out["swing_status"] = _text_col(df, "Status")
    out["swing_score"] = _num(df["Score"]) if "Score" in df.columns else np.nan
    out["swing_primary_signal"] = _text_col(df, "Primary_Signal")
    out["swing_present"] = True
    for h in MILESTONES:
        col = f"D+{h}_Close_Return_Pct"
        out[f"swing_ret_D{h}"] = _num(df[col]) / 100.0 if col in df.columns else np.nan
    out["swing_mfe_D60"] = _num(df["MFE_60D_Pct"]) / 100.0 if "MFE_60D_Pct" in df.columns else np.nan
    out["swing_mae_D60"] = _num(df["MAE_60D_Pct"]) / 100.0 if "MAE_60D_Pct" in df.columns else np.nan
    return (
        out.dropna(subset=["signal_date", "ticker"])
        .sort_values(["signal_date", "ticker", "swing_score"], ascending=[True, True, False])
        .drop_duplicates(["signal_date", "ticker"], keep="first")
    )


def _read_kjb(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    out = pd.DataFrame(index=df.index)
    out["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce").dt.normalize()
    out["ticker"] = df["ticker"].map(_ticker)
    out["name_kjb"] = _text_col(df, "name")
    out["market_kjb"] = _text_col(df, "market")
    out["kjb_score"] = _num(df["selection_score"]) if "selection_score" in df.columns else np.nan
    out["kjb_technical_score"] = _num(df["technical_score"]) if "technical_score" in df.columns else np.nan
    out["kjb_timing_score"] = _num(df["timing_score"]) if "timing_score" in df.columns else np.nan
    out["kjb_risk_score"] = _num(df["risk_score"]) if "risk_score" in df.columns else np.nan
    out["kjb_rs_score"] = _num(df["relative_strength_score"]) if "relative_strength_score" in df.columns else np.nan
    out["kjb_leader_score"] = _num(df["leader_score"]) if "leader_score" in df.columns else np.nan
    out["kjb_sector_leader_score"] = _num(df["sector_leader_score"]) if "sector_leader_score" in df.columns else np.nan
    out["kjb_true_leader"] = df["is_true_leader"] if "is_true_leader" in df.columns else False
    out["kjb_present"] = True
    for h in MILESTONES:
        col = f"D+{h}"
        out[f"kjb_ret_D{h}"] = _num(df[col]) if col in df.columns else np.nan
    out["kjb_mfe_D60"] = _num(df["MFE_D+60"]) if "MFE_D+60" in df.columns else np.nan
    out["kjb_mae_D60"] = _num(df["MAE_D+60"]) if "MAE_D+60" in df.columns else np.nan
    return (
        out.dropna(subset=["signal_date", "ticker"])
        .sort_values(["signal_date", "ticker", "kjb_score"], ascending=[True, True, False])
        .drop_duplicates(["signal_date", "ticker"], keep="first")
    )


def _read_universe_market(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    ticker_col = "ticker" if "ticker" in df.columns else "Ticker"
    market_col = "market" if "market" in df.columns else "Market"
    if ticker_col not in df.columns or market_col not in df.columns:
        raise ValueError(f"Universe ticker/market 컬럼 누락: {path}")
    out = pd.DataFrame({
        "ticker": df[ticker_col].map(_ticker),
        "market": df[market_col].map(_normalize_market),
    })
    return out[out["market"].ne("")].drop_duplicates("ticker", keep="first")


def _read_market_regime(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    required = {"date", "market", "market_regime"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"market_regime_daily 필수 컬럼 누락 {sorted(missing)}: {path}")
    out = df.copy()
    out["signal_date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["market"] = out["market"].map(_normalize_market)
    out["market_regime"] = out["market_regime"].fillna("unknown").astype(str).str.lower()
    keep = ["signal_date", "market", "market_regime"]
    for col in [
        "benchmark", "index_close", "index_return_5d", "index_return_20d",
        "index_drawdown_20d", "index_ma20_gap", "index_ma60_gap",
        "index_volatility_20d", "index_volatility_120d",
        "breadth_stock_count", "breadth_valid_ma20", "breadth_valid_ma60",
        "breadth_above_ma20_ratio", "breadth_above_ma60_ratio",
        "breadth_positive_5d_ratio", "breadth_positive_20d_ratio",
        "history_bars", "regime_warning",
    ]:
        if col in out.columns:
            keep.append(col)
    return (
        out[keep]
        .dropna(subset=["signal_date"])
        .loc[lambda x: x["market"].ne("")]
        .drop_duplicates(["signal_date", "market"], keep="last")
    )


def _combine(swing: pd.DataFrame, kjb: pd.DataFrame) -> pd.DataFrame:
    """두 Analyzer 후보를 한 pool로 합친다.

    동일 날짜/티커가 두 Analyzer에 동시에 있어도 별도 합의(BOTH) 보너스를 주지 않는다.
    두 점수가 모두 있으면 base_strength는 단순 평균, 한쪽만 있으면 그 점수를 사용한다.
    """
    x = swing.merge(kjb, on=["signal_date", "ticker"], how="outer")
    x["swing_present"] = x["swing_present"].fillna(False).astype(bool)
    x["kjb_present"] = x["kjb_present"].fillna(False).astype(bool)
    x["source_count"] = x[["swing_present", "kjb_present"]].astype(int).sum(axis=1)

    x["name"] = x["name_swing"].where(
        x["name_swing"].notna() & x["name_swing"].ne(""),
        x["name_kjb"],
    )

    scores = pd.concat([x["swing_score"], x["kjb_score"]], axis=1)
    x["base_strength"] = scores.mean(axis=1, skipna=True)

    risk = x["kjb_risk_score"]
    x["risk_penalty"] = (((risk - 50.0).clip(lower=0.0) * 0.15).clip(upper=7.5)).fillna(0.0)
    x["combined_score"] = (x["base_strength"] - x["risk_penalty"]).clip(0, 100)

    mismatch_flags = []
    for h in MILESTONES:
        s = x[f"swing_ret_D{h}"]
        k = x[f"kjb_ret_D{h}"]
        x[f"ret_D{h}"] = s.where(s.notna(), k)
        x[f"return_diff_D{h}"] = (s - k).abs().where(s.notna() & k.notna())
        mismatch_flags.append(x[f"return_diff_D{h}"].gt(0.001).fillna(False))
    x["return_source_mismatch"] = pd.concat(mismatch_flags, axis=1).any(axis=1)

    x["mfe_D60"] = x["swing_mfe_D60"].where(x["swing_mfe_D60"].notna(), x["kjb_mfe_D60"])
    x["mae_D60"] = x["swing_mae_D60"].where(x["swing_mae_D60"].notna(), x["kjb_mae_D60"])
    return x.sort_values(["signal_date", "combined_score"], ascending=[True, False]).reset_index(drop=True)


def _attach_market_regime(
    combined: pd.DataFrame,
    universe_market: pd.DataFrame,
    regime_daily: pd.DataFrame,
) -> pd.DataFrame:
    x = combined.copy()
    market_map = (
        universe_market.set_index("ticker")["market"]
        if not universe_market.empty else pd.Series(dtype=str)
    )
    kjb_market = (
        x["market_kjb"].map(_normalize_market)
        if "market_kjb" in x.columns else pd.Series("", index=x.index)
    )
    x["market"] = kjb_market
    missing_market = x["market"].eq("")
    if missing_market.any() and not market_map.empty:
        x.loc[missing_market, "market"] = (
            x.loc[missing_market, "ticker"].map(market_map).fillna("")
        )

    regime_cols = [c for c in regime_daily.columns if c != "date"]
    x = x.merge(regime_daily[regime_cols], on=["signal_date", "market"], how="left")
    x["market_regime"] = x["market_regime"].fillna("unknown").astype(str).str.lower()
    return x.sort_values(["signal_date", "combined_score"], ascending=[True, False]).reset_index(drop=True)


def _daily_top(frame: pd.DataFrame, n: int) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    ranked = frame.sort_values(
        ["signal_date", "combined_score", "ticker"], ascending=[True, False, True]
    ).copy()
    ranked["daily_rank"] = ranked.groupby("signal_date").cumcount() + 1
    return ranked[ranked["daily_rank"] <= n].copy()


def _event_summary(cohorts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, frame in cohorts.items():
        for h in MILESTONES:
            col = f"ret_D{h}"
            v = _num(frame[col]).dropna() if col in frame.columns else pd.Series(dtype=float)
            rows.append({
                "cohort": name,
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


def _date_equal_summary(cohorts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, frame in cohorts.items():
        for h in MILESTONES:
            col = f"ret_D{h}"
            basket = (
                frame.groupby("signal_date")[col].mean().dropna()
                if (not frame.empty and col in frame.columns)
                else pd.Series(dtype=float)
            )
            rows.append({
                "cohort": name,
                "horizon": h,
                "date_count": int(len(basket)),
                "avg_basket_return": float(basket.mean()) if len(basket) else np.nan,
                "median_basket_return": float(basket.median()) if len(basket) else np.nan,
                "positive_date_rate": float((basket > 0).mean()) if len(basket) else np.nan,
            })
    return pd.DataFrame(rows)


def _regime_event_summary(cohorts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict] = []
    for cohort, frame in cohorts.items():
        scopes = [("ALL", frame)]
        if "market" in frame.columns:
            scopes.extend((market, grp) for market, grp in frame.groupby("market") if market)
        for market, scoped in scopes:
            if scoped.empty or "market_regime" not in scoped.columns:
                continue
            for regime, grp in scoped.groupby("market_regime", dropna=False):
                regime_name = str(regime or "unknown").lower()
                for h in MILESTONES:
                    col = f"ret_D{h}"
                    v = _num(grp[col]).dropna() if col in grp.columns else pd.Series(dtype=float)
                    rows.append({
                        "cohort": cohort,
                        "market": market,
                        "market_regime": regime_name,
                        "horizon": h,
                        "signal_count": int(len(grp)),
                        "valid_count": int(len(v)),
                        "avg_return": float(v.mean()) if len(v) else np.nan,
                        "median_return": float(v.median()) if len(v) else np.nan,
                        "win_rate": float((v > 0).mean()) if len(v) else np.nan,
                        "p25_return": float(v.quantile(0.25)) if len(v) else np.nan,
                        "p75_return": float(v.quantile(0.75)) if len(v) else np.nan,
                    })
    return pd.DataFrame(rows)


def _regime_date_equal_summary(cohorts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict] = []
    for cohort, frame in cohorts.items():
        scopes = [("ALL", frame)]
        if "market" in frame.columns:
            scopes.extend((market, grp) for market, grp in frame.groupby("market") if market)
        for market, scoped in scopes:
            if scoped.empty or "market_regime" not in scoped.columns:
                continue
            for regime, grp in scoped.groupby("market_regime", dropna=False):
                regime_name = str(regime or "unknown").lower()
                for h in MILESTONES:
                    col = f"ret_D{h}"
                    basket = (
                        grp.groupby("signal_date")[col].mean().dropna()
                        if col in grp.columns else pd.Series(dtype=float)
                    )
                    rows.append({
                        "cohort": cohort,
                        "market": market,
                        "market_regime": regime_name,
                        "horizon": h,
                        "date_count": int(len(basket)),
                        "avg_basket_return": float(basket.mean()) if len(basket) else np.nan,
                        "median_basket_return": float(basket.median()) if len(basket) else np.nan,
                        "positive_date_rate": float((basket > 0).mean()) if len(basket) else np.nan,
                    })
    return pd.DataFrame(rows)


def _fmt_event(event_summary: pd.DataFrame, cohort: str, horizon: int) -> str:
    row = event_summary[
        (event_summary["cohort"] == cohort) & (event_summary["horizon"] == horizon)
    ]
    if row.empty or pd.isna(row.iloc[0]["avg_return"]):
        return "-"
    r = row.iloc[0]
    return f"{r['avg_return']*100:.2f}% / win {r['win_rate']*100:.1f}%"


def _write_markdown(
    path: Path,
    event_summary: pd.DataFrame,
    date_summary: pd.DataFrame,
    regime_event_summary: pd.DataFrame,
    quality: pd.DataFrame,
    daily_top_n: int,
) -> None:
    combined_name = f"COMBINED_TOP{daily_top_n}"
    cohorts = ["SIYOON_ALL", "KJB_ALL", combined_name]
    lines = [
        "# Combined Range Backtest",
        "",
        "두 Analyzer 후보를 같은 날짜+티커 기준으로 하나의 후보 Pool로 결합해 비교한 결과다.",
        "",
        "- 같은 종목을 두 Analyzer가 동시에 포착해도 별도 합의 보너스나 우선권을 주지 않는다.",
        f"- {combined_name}: 후보 Pool에서 일별 종합점수 상위 {daily_top_n}개",
        "- 종합점수는 available Analyzer score 평균에서 KJB Risk penalty만 차감하는 deterministic proxy다.",
        "- 시장 Regime은 KOSPI/KOSDAQ별로 각 과거 날짜 시점까지의 데이터만 사용한다.",
        "",
        "## 핵심 성과 (Event-weighted)",
        "",
        "| Cohort | D+5 | D+20 | D+60 |",
        "|---|---:|---:|---:|",
    ]
    for cohort in cohorts:
        lines.append(
            f"| {cohort} | {_fmt_event(event_summary, cohort, 5)} | "
            f"{_fmt_event(event_summary, cohort, 20)} | {_fmt_event(event_summary, cohort, 60)} |"
        )

    lines.extend([
        "",
        "## Date-equal weighted",
        "",
        "각 날짜에 선택된 종목을 동일가중 바스켓으로 본 뒤 날짜별 평균을 다시 집계한다.",
        "",
    ])
    for cohort in cohorts:
        row = date_summary[
            (date_summary["cohort"] == cohort) & (date_summary["horizon"] == 20)
        ]
        if not row.empty and pd.notna(row.iloc[0]["avg_basket_return"]):
            r = row.iloc[0]
            lines.append(
                f"- {cohort} D+20: avg={r['avg_basket_return']*100:.2f}%, "
                f"positive_dates={r['positive_date_rate']*100:.1f}%, "
                f"dates={int(r['date_count'])}"
            )

    lines.extend([
        "",
        "## 시장 Regime별 D+20 (Event-weighted, ALL market)",
        "",
        "| Cohort | Regime | Signals | Avg D+20 | Win Rate |",
        "|---|---|---:|---:|---:|",
    ])
    for cohort in cohorts:
        view = regime_event_summary[
            (regime_event_summary["cohort"] == cohort)
            & (regime_event_summary["market"] == "ALL")
            & (regime_event_summary["horizon"] == 20)
        ] if not regime_event_summary.empty else pd.DataFrame()
        for _, r in view.sort_values("market_regime").iterrows():
            avg = "-" if pd.isna(r["avg_return"]) else f"{r['avg_return']*100:.2f}%"
            win = "-" if pd.isna(r["win_rate"]) else f"{r['win_rate']*100:.1f}%"
            lines.append(
                f"| {cohort} | {r['market_regime']} | {int(r['valid_count'])} | {avg} | {win} |"
            )

    lines.extend(["", "## Data Quality", ""])
    for _, r in quality.iterrows():
        lines.append(f"- {r['metric']}: {r['value']}")

    lines.extend([
        "",
        "## 주의",
        "",
        "- KJB Range는 현재 KOSPI_Info.xlsx 스냅샷 Universe를 과거에 적용하므로 survivorship/universe bias가 남는다.",
        "- 같은 종목의 연속 일별 신호는 독립 표본이 아니다. Event-weighted와 Date-equal 결과를 함께 본다.",
        "- 동일 종목이 두 Analyzer에 동시에 존재한다는 사실 자체는 점수/후보선택에 보너스로 사용하지 않는다.",
        "- 시장 Regime은 현재 Combined Score에는 가감하지 않는다.",
        "- 이 결과로 종합 가중치를 튜닝하면 별도 holdout 기간에서 다시 검증해야 한다.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Combine Siyoon + KJB range backtests without consensus/BOTH bonus"
    )
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--daily-top-n", type=int, default=5)
    p.add_argument("--swing-file", default="")
    p.add_argument("--kjb-file", default="")
    p.add_argument("--universe-file", default="")
    p.add_argument("--market-regime-file", default="")
    p.add_argument("--output-root", default=str(ROOT / "results"))
    args = p.parse_args()

    start, end = args.date_range.replace(" ", "").split("~", 1)
    range_key = f"{start}_{end}"
    swing_range_dir = ROOT / "SwingChartProbabilityAnalyzer" / "results" / f"range_{range_key}"
    kjb_range_dir = ROOT / "KJBChartAnalyzer" / "results" / f"range_{range_key}"
    swing_path = Path(args.swing_file) if args.swing_file else swing_range_dir / "range_candidates.csv"
    kjb_path = Path(args.kjb_file) if args.kjb_file else kjb_range_dir / "chart_range_events.csv"
    universe_path = Path(args.universe_file) if args.universe_file else kjb_range_dir / "universe.csv"
    regime_path = (
        Path(args.market_regime_file)
        if args.market_regime_file else kjb_range_dir / "market_regime_daily.csv"
    )

    for label, path in [
        ("Swing range", swing_path),
        ("KJB range", kjb_path),
        ("Universe", universe_path),
        ("Market regime", regime_path),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"{label} file not found: {path}")

    swing = _read_swing(swing_path)
    kjb = _read_kjb(kjb_path)
    universe_market = _read_universe_market(universe_path)
    regime_daily = _read_market_regime(regime_path)

    combined = _attach_market_regime(
        _combine(swing, kjb), universe_market, regime_daily
    )
    combined_top = _daily_top(combined, args.daily_top_n)

    cohorts = {
        "SIYOON_ALL": combined[combined["swing_present"]].copy(),
        "KJB_ALL": combined[combined["kjb_present"]].copy(),
        f"COMBINED_TOP{args.daily_top_n}": combined_top,
    }
    event_summary = _event_summary(cohorts)
    date_summary = _date_equal_summary(cohorts)
    regime_event_summary = _regime_event_summary(cohorts)
    regime_date_summary = _regime_date_equal_summary(cohorts)

    market_missing = int(combined["market"].eq("").sum())
    regime_missing = int(combined["market_regime"].eq("unknown").sum())
    quality = pd.DataFrame([
        {"metric": "siyoon_signals", "value": len(swing)},
        {"metric": "kjb_signals", "value": len(kjb)},
        {"metric": "union_signals", "value": len(combined)},
        {
            "metric": "return_source_mismatch_rows",
            "value": int(combined["return_source_mismatch"].sum()),
        },
        {"metric": "market_missing_rows", "value": market_missing},
        {"metric": "market_regime_unknown_rows", "value": regime_missing},
        {
            "metric": "market_regime_usage",
            "value": "analysis-only; not used in combined_score",
        },
        {
            "metric": "combined_score_formula",
            "value": "mean(available analyzer scores) - max(KJB risk-50,0)*0.15 (cap 7.5); no consensus/BOTH bonus",
        },
    ])

    out_dir = Path(args.output_root) / f"combined_range_{range_key}"
    out_dir.mkdir(parents=True, exist_ok=True)

    stale = out_dir / "both_agree_events.csv"
    if stale.exists():
        stale.unlink()

    combined.to_csv(out_dir / "combined_events.csv", index=False, encoding="utf-8-sig")
    combined_top.to_csv(
        out_dir / f"combined_daily_top{args.daily_top_n}.csv",
        index=False,
        encoding="utf-8-sig",
    )
    event_summary.to_csv(
        out_dir / "performance_event_weighted.csv", index=False, encoding="utf-8-sig"
    )
    date_summary.to_csv(
        out_dir / "performance_date_equal.csv", index=False, encoding="utf-8-sig"
    )
    regime_event_summary.to_csv(
        out_dir / "performance_by_regime_event.csv", index=False, encoding="utf-8-sig"
    )
    regime_date_summary.to_csv(
        out_dir / "performance_by_regime_date_equal.csv", index=False, encoding="utf-8-sig"
    )
    regime_daily.to_csv(
        out_dir / "market_regime_daily.csv", index=False, encoding="utf-8-sig"
    )
    quality.to_csv(out_dir / "data_quality.csv", index=False, encoding="utf-8-sig")

    xlsx_path = out_dir / "combined_range_backtest.xlsx"
    try:
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            combined.to_excel(writer, sheet_name="combined_events", index=False)
            combined_top.to_excel(writer, sheet_name="combined_daily_top", index=False)
            event_summary.to_excel(writer, sheet_name="event_summary", index=False)
            date_summary.to_excel(writer, sheet_name="date_equal_summary", index=False)
            regime_event_summary.to_excel(writer, sheet_name="regime_event_summary", index=False)
            regime_date_summary.to_excel(writer, sheet_name="regime_date_summary", index=False)
            regime_daily.to_excel(writer, sheet_name="market_regime_daily", index=False)
            quality.to_excel(writer, sheet_name="data_quality", index=False)
    except Exception as exc:
        print(f"[WARN] Excel output skipped: {exc}")

    md_path = out_dir / "combined_range_summary.md"
    _write_markdown(
        md_path,
        event_summary,
        date_summary,
        regime_event_summary,
        quality,
        args.daily_top_n,
    )

    print("\n[COMBINED RANGE BACKTEST - NO CONSENSUS BONUS]")
    view = event_summary[event_summary["horizon"].isin([5, 20, 60])].copy()
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

    print("\n[REGIME D+20 - ALL MARKET]")
    rv = regime_event_summary[
        (regime_event_summary["market"] == "ALL")
        & (regime_event_summary["horizon"] == 20)
    ].copy()
    if not rv.empty:
        rv["avg_return"] = rv["avg_return"].map(
            lambda v: "-" if pd.isna(v) else f"{v*100:.2f}%"
        )
        rv["win_rate"] = rv["win_rate"].map(
            lambda v: "-" if pd.isna(v) else f"{v*100:.1f}%"
        )
        print(
            rv[["cohort", "market_regime", "valid_count", "avg_return", "win_rate"]]
            .sort_values(["cohort", "market_regime"])
            .to_string(index=False)
        )

    print("\nOutput:", out_dir)
    print("Summary:", md_path)
    print("Regime event:", out_dir / "performance_by_regime_event.csv")
    print("Regime date :", out_dir / "performance_by_regime_date_equal.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
