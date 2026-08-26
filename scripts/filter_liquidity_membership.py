from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _ticker(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _parse_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    raw = str(text or "").strip().replace(" ", "")
    if "~" not in raw:
        raise ValueError("--date-range은 YYYYMMDD~YYYYMMDD 형식이어야 합니다.")
    left, right = raw.split("~", 1)
    start = pd.to_datetime(left, format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(right, format="%Y%m%d", errors="raise").normalize()
    return start, end, f"{start:%Y%m%d}_{end:%Y%m%d}"


def _read_membership(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Liquidity membership CSV가 없습니다: {p}")
    m = pd.read_csv(p, encoding="utf-8-sig", dtype={"ticker": str})
    required = {"date", "ticker", "source_rank", "avg_trading_value_20d"}
    missing = required - set(m.columns)
    if missing:
        raise ValueError(f"Membership 필수 컬럼 누락: {sorted(missing)}")
    m = m.copy()
    m["date"] = pd.to_datetime(m["date"], errors="coerce").dt.normalize()
    m["ticker"] = m["ticker"].map(_ticker)
    m = m.dropna(subset=["date"]).drop_duplicates(["date", "ticker"], keep="last")
    return m


def _membership_for_merge(m: pd.DataFrame, date_col: str, ticker_col: str) -> pd.DataFrame:
    cols = ["date", "ticker", "source_rank", "avg_trading_value_20d"]
    for optional in ["trading_value", "universe_cutoff_value", "lookback_days", "market", "name"]:
        if optional in m.columns:
            cols.append(optional)
    x = m[cols].copy()
    rename = {
        "date": date_col,
        "ticker": ticker_col,
        "source_rank": "universe_rank",
        "avg_trading_value_20d": "avg_trading_value_20d",
        "trading_value": "trading_value_today",
    }
    return x.rename(columns=rename)


def _filter_frame(
    df: pd.DataFrame,
    membership: pd.DataFrame,
    date_col: str,
    ticker_col: str,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    x = df.copy()
    x[date_col] = pd.to_datetime(x[date_col], errors="coerce").dt.normalize()
    x[ticker_col] = x[ticker_col].map(_ticker)

    injected = [
        "universe_rank",
        "avg_trading_value_20d",
        "trading_value_today",
        "universe_cutoff_value",
        "lookback_days",
    ]
    x = x.drop(columns=[c for c in injected if c in x.columns], errors="ignore")
    m = _membership_for_merge(membership, date_col, ticker_col)
    out = x.merge(m, on=[date_col, ticker_col], how="inner", suffixes=("", "_liquidity"))
    return out


def _build_forward_summary(events: pd.DataFrame, forward_bars: int) -> pd.DataFrame:
    rows: list[dict] = []
    for h in range(1, forward_bars + 1):
        col = f"D+{h}"
        if col not in events.columns:
            values = pd.Series(dtype=float)
        else:
            values = pd.to_numeric(events[col], errors="coerce").dropna()
        rows.append(
            {
                "horizon": f"D+{h}",
                "trading_days": h,
                "valid_count": int(len(values)),
                "avg_return": float(values.mean()) if len(values) else np.nan,
                "median_return": float(values.median()) if len(values) else np.nan,
                "win_rate": float((values > 0).mean()) if len(values) else np.nan,
                "loss_rate": float((values < 0).mean()) if len(values) else np.nan,
                "std_return": float(values.std()) if len(values) > 1 else np.nan,
                "best_return": float(values.max()) if len(values) else np.nan,
                "worst_return": float(values.min()) if len(values) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _build_status_summary(events: pd.DataFrame, forward_bars: int) -> pd.DataFrame:
    cohorts = [("KJB_ALL", events)]
    if "Status" in events.columns:
        cohorts.extend(
            [
                ("KJB_CONFIRMED", events[events["Status"].eq("CONFIRMED")]),
                ("KJB_WATCH", events[events["Status"].eq("WATCH")]),
                ("KJB_REJECTED", events[events["Status"].eq("REJECTED")]),
            ]
        )
    parts = []
    for name, frame in cohorts:
        s = _build_forward_summary(frame, forward_bars)
        s.insert(0, "cohort", name)
        parts.append(s)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _recalc_kjb_ranks(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events
    x = events.copy()
    rank_specs = [
        ("daily_rank", "selection_score", ["signal_date"]),
        ("daily_strength_rank", "relative_strength_score", ["signal_date"]),
        ("daily_leader_rank", "leader_score", ["signal_date"]),
        ("daily_sector_leader_rank", "sector_leader_score", ["signal_date"]),
        ("sector_stock_rs_rank", "relative_strength_score", ["signal_date", "sector_name"]),
        ("sector_stock_leader_rank", "sector_leader_score", ["signal_date", "sector_name"]),
    ]
    for target, score, groups in rank_specs:
        if score not in x.columns or any(g not in x.columns for g in groups):
            continue
        x[target] = (
            x.groupby(groups, dropna=False)[score]
            .rank(method="first", ascending=False, na_option="bottom")
            .astype("Int64")
        )
    sort_cols = [c for c in ["signal_date", "daily_sector_leader_rank", "sector_leader_score"] if c in x.columns]
    if sort_cols:
        ascending = [True] + [True] * (len(sort_cols) - 1)
        if sort_cols[-1] == "sector_leader_score":
            ascending[-1] = False
        x = x.sort_values(sort_cols, ascending=ascending)
    return x.reset_index(drop=True)


def _rebuild_kjb_breadth(
    membership: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    forward_bars: int,
) -> pd.DataFrame:
    kjb_root = ROOT / "KJBChartAnalyzer"
    sys.path.insert(0, str(kjb_root))
    try:
        from chartsel.data.pykrx_provider import PykrxDataProvider
    finally:
        if sys.path and sys.path[0] == str(kjb_root):
            sys.path.pop(0)

    provider = PykrxDataProvider(cache_dir=kjb_root / "cache", use_cache=True)
    fetch_start = (start - pd.Timedelta(days=1200)).strftime("%Y-%m-%d")
    fetch_end = (end + pd.Timedelta(days=max(120, int(forward_bars * 2)))).strftime("%Y-%m-%d")

    target_keys = membership[["date", "ticker", "market"]].copy()
    target_keys["ticker"] = target_keys["ticker"].map(_ticker)
    records: list[pd.DataFrame] = []

    meta = target_keys[["ticker", "market"]].drop_duplicates("ticker", keep="last")
    for idx, row in enumerate(meta.itertuples(index=False), start=1):
        ticker = _ticker(row.ticker)
        try:
            raw = provider.get_ohlcv_by_date(ticker, fetch_start, fetch_end)
        except Exception as exc:
            print(f"[WARN] breadth {ticker} 조회 실패: {exc}")
            continue
        if raw is None or raw.empty:
            continue
        x = raw.copy()
        x.index = pd.to_datetime(x.index).normalize()
        x = x[~x.index.duplicated(keep="last")].sort_index()
        close = pd.to_numeric(x["Close"], errors="coerce")
        ma20 = close.rolling(20, min_periods=20).mean()
        ma60 = close.rolling(60, min_periods=60).mean()
        ret5 = close.pct_change(5)
        ret20 = close.pct_change(20)
        frame = pd.DataFrame(
            {
                "date": x.index,
                "ticker": ticker,
                "above_ma20": np.where(ma20.notna(), (close > ma20).astype(float), np.nan),
                "above_ma60": np.where(ma60.notna(), (close > ma60).astype(float), np.nan),
                "positive_5d": np.where(ret5.notna(), (ret5 > 0).astype(float), np.nan),
                "positive_20d": np.where(ret20.notna(), (ret20 > 0).astype(float), np.nan),
            }
        )
        own_keys = target_keys[target_keys["ticker"].eq(ticker)][["date", "ticker", "market"]]
        frame = frame.merge(own_keys, on=["date", "ticker"], how="inner")
        if not frame.empty:
            records.append(frame)
        if idx % 50 == 0:
            print(f"[LIQUIDITY FILTER] breadth {idx}/{len(meta)}")

    if not records:
        return pd.DataFrame()

    detail = pd.concat(records, ignore_index=True)
    return (
        detail.groupby(["date", "market"], as_index=False)
        .agg(
            breadth_stock_count=("ticker", "nunique"),
            breadth_valid_ma20=("above_ma20", "count"),
            breadth_valid_ma60=("above_ma60", "count"),
            breadth_above_ma20_ratio=("above_ma20", "mean"),
            breadth_above_ma60_ratio=("above_ma60", "mean"),
            breadth_positive_5d_ratio=("positive_5d", "mean"),
            breadth_positive_20d_ratio=("positive_20d", "mean"),
        )
        .sort_values(["date", "market"])
        .reset_index(drop=True)
    )


def _filter_kjb(args, membership: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, key: str) -> None:
    out_dir = ROOT / "KJBChartAnalyzer" / "results" / f"range_{key}"
    events_path = out_dir / "chart_range_events.csv"
    if not events_path.exists():
        raise FileNotFoundError(events_path)

    raw = pd.read_csv(events_path, encoding="utf-8-sig", dtype={"ticker": str})
    before = len(raw)
    events = _filter_frame(raw, membership, "signal_date", "ticker")
    events = _recalc_kjb_ranks(events)
    after = len(events)

    summary = _build_forward_summary(events, args.forward_bars)
    status_summary = _build_status_summary(events, args.forward_bars)

    events.to_csv(events_path, index=False, encoding="utf-8-sig")
    summary.to_csv(out_dir / "chart_range_summary_D1_D60.csv", index=False, encoding="utf-8-sig")
    status_summary.to_csv(out_dir / "chart_range_status_summary_D1_D60.csv", index=False, encoding="utf-8-sig")

    breadth = _rebuild_kjb_breadth(membership, start, end, args.forward_bars)
    breadth.to_csv(out_dir / "market_breadth_daily.csv", index=False, encoding="utf-8-sig")
    regime_path = out_dir / "market_regime_daily.csv"
    if regime_path.exists() and not breadth.empty:
        regime = pd.read_csv(regime_path, encoding="utf-8-sig")
        regime["date"] = pd.to_datetime(regime["date"], errors="coerce").dt.normalize()
        breadth_cols = [c for c in regime.columns if c.startswith("breadth_")]
        regime = regime.drop(columns=breadth_cols, errors="ignore")
        regime = regime.merge(breadth, on=["date", "market"], how="left")
        regime.to_csv(regime_path, index=False, encoding="utf-8-sig")

    # Excel/HTML도 필터 후 CSV와 같은 내용으로 다시 작성한다.
    kjb_root = ROOT / "KJBChartAnalyzer"
    sys.path.insert(0, str(kjb_root))
    try:
        from chartsel.backtest.range_report import save_range_backtest_excel, save_range_backtest_html
        universe_path = out_dir / "universe.csv"
        errors_path = out_dir / "errors.csv"
        universe = pd.read_csv(universe_path, encoding="utf-8-sig", dtype={"ticker": str}) if universe_path.exists() else pd.DataFrame()
        errors = pd.read_csv(errors_path, encoding="utf-8-sig") if errors_path.exists() else pd.DataFrame()
        status_counts = events["Status"].value_counts() if "Status" in events.columns else pd.Series(dtype="int64")
        meta = {
            "기간": f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}",
            "Universe": f"최근 {args.lookback}거래일 평균 거래대금 일별 TOP {args.top_n}",
            "Universe 방식": "point-in-time; 각 신호일 당시 정보만 사용",
            "신호수": len(events),
            "CONFIRMED 수": int(status_counts.get("CONFIRMED", 0)),
            "WATCH 수": int(status_counts.get("WATCH", 0)),
            "REJECTED 수": int(status_counts.get("REJECTED", 0)),
            "D+수익률": f"D+1 ~ D+{args.forward_bars} 거래일",
        }
        xlsx = out_dir / "chart_range_backtest.xlsx"
        html = out_dir / "chart_range_backtest.html"
        save_range_backtest_excel(events, summary, universe, errors, xlsx, meta)
        with pd.ExcelWriter(xlsx, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            status_summary.to_excel(writer, sheet_name="Status별통계", index=False)
        save_range_backtest_html(events, summary, html, meta)
    finally:
        if sys.path and sys.path[0] == str(kjb_root):
            sys.path.pop(0)

    print(f"[DONE] KJB liquidity filter: {before} -> {after} rows | {events_path}")


def _filter_swing(args, membership: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, key: str) -> None:
    swing_root = ROOT / "SwingChartProbabilityAnalyzer"
    out_dir = swing_root / "results" / f"range_{key}"
    all_path = out_dir / "range_all_results.csv"
    if not all_path.exists():
        raise FileNotFoundError(all_path)

    raw = pd.read_csv(all_path, encoding="utf-8-sig", dtype={"Ticker": str})
    before = len(raw)
    all_results = _filter_frame(raw, membership, "Actual_Date", "Ticker")
    after = len(all_results)
    candidates = all_results[all_results["Status"].isin(["STRONG_CONFIRMED", "CONFIRMED", "WATCH"])].copy()

    all_results.to_csv(all_path, index=False, encoding="utf-8-sig")
    candidates.to_csv(out_dir / "range_candidates.csv", index=False, encoding="utf-8-sig")

    # 기존 config 시트를 보존하면서 workbook/agent summary를 필터 결과로 재생성한다.
    xlsx = out_dir / "swing_range_backtest.xlsx"
    config_rows = []
    if xlsx.exists():
        try:
            config_rows = pd.read_excel(xlsx, sheet_name="config").to_dict("records")
        except Exception:
            config_rows = []
    config_rows.extend(
        [
            {"Parameter": "universe_mode", "Value": f"liquidity_{args.lookback}d_top{args.top_n}_point_in_time"},
            {"Parameter": "membership_csv", "Value": str(Path(args.membership_csv).resolve())},
        ]
    )

    sys.path.insert(0, str(swing_root))
    try:
        writer_mod = importlib.import_module("reporting.range_excel_writer")
        exporter_mod = importlib.import_module("reporting.range_agent_exporter")
        writer_mod.write_range_workbook(xlsx, all_results, config_rows, forward_bars=args.forward_bars)
        exporter_mod.export_range_agent_summary(
            candidates,
            out_dir,
            range_start=start.strftime("%Y-%m-%d"),
            range_end=end.strftime("%Y-%m-%d"),
            forward_bars=args.forward_bars,
        )
    finally:
        if sys.path and sys.path[0] == str(swing_root):
            sys.path.pop(0)

    print(f"[DONE] Siyoon liquidity filter: {before} -> {after} rows | {all_path}")


def main() -> int:
    p = argparse.ArgumentParser(description="Range analyzer 결과를 일별 거래대금 TOP N membership으로 필터")
    p.add_argument("--analyzer", choices=["kjb", "swing"], required=True)
    p.add_argument("--date-range", required=True)
    p.add_argument("--membership-csv", required=True)
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--lookback", type=int, default=20)
    p.add_argument("--forward-bars", type=int, default=60)
    args = p.parse_args()

    start, end, key = _parse_range(args.date_range)
    membership = _read_membership(args.membership_csv)
    membership = membership[(membership["date"] >= start) & (membership["date"] <= end)].copy()
    if membership.empty:
        raise RuntimeError("입력 기간의 liquidity membership이 비어 있습니다.")

    if args.analyzer == "kjb":
        _filter_kjb(args, membership, start, end, key)
    else:
        _filter_swing(args, membership, start, end, key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
