from __future__ import annotations

"""DynamicChartAnalyzer LONG V2 range backtest.

V2 preserves the original Stage1 -> Stage2 -> Stage3 entry state machine and fixed
1:2:7 position plan. It enriches every range event with causal research features,
cross-sectional relative-strength percentiles, LONG quality scoring, market regime,
chase risk, and daily LONG ranking.

The original main_range.py remains available as V1 for exact before/after comparison.
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd

import main_range as v1
from dynamic_chart_analyzer import DynamicChartAnalyzer, StrategyConfig
from dynamic_chart_analyzer.long_v2 import (
    BASE_EVENT_FEATURE_COLUMNS,
    BENCHMARK_PROXY,
    add_long_v2_features,
    add_rs_percentiles,
    prepare_market_features,
    score_long_events,
)

ROOT = Path(__file__).resolve().parent

# Public aliases intentionally exist so main_range_kjb.py can patch these two market
# access points exactly as it patched V1.
_latest_market_date = v1._latest_market_date
_get_universe = v1._get_universe
load_pykrx = v1.load_pykrx


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    return v1._normalize_ohlcv(df)


def _direction(action: str) -> int:
    return v1._direction(action)


def _add_forward_metrics(event: dict, price_df: pd.DataFrame, forward_bars: int) -> dict:
    return v1._add_forward_metrics(event, price_df, forward_bars)


def _build_summary(events: pd.DataFrame, forward_bars: int) -> pd.DataFrame:
    return v1._build_summary(events, forward_bars)


def _scalar(value):
    if isinstance(value, pd.Series):
        if value.empty:
            return np.nan
        value = value.iloc[-1]
    if value is pd.NA:
        return np.nan
    return value


def _build_long_v2_summary(events: pd.DataFrame, forward_bars: int) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["long_quality_label", "stage", "count"])

    long_df = events[events["side"].eq("LONG")].copy()
    if long_df.empty:
        return pd.DataFrame(columns=["long_quality_label", "stage", "count"])

    horizons = [h for h in [1, 5, 10, 20, 40, 60] if h <= forward_bars]
    rows: list[dict] = []
    label_order = {"CONFIRMED": 0, "WATCH": 1, "REJECT": 2}

    grouped = long_df.groupby(["long_quality_label", "stage"], dropna=False)
    for (label, stage), g in grouped:
        row: dict[str, object] = {
            "long_quality_label": label,
            "stage": int(stage),
            "count": int(len(g)),
            "complete_count": int(g["forward_complete"].fillna(False).sum()),
            "avg_quality_score": float(pd.to_numeric(g["long_quality_score"], errors="coerce").mean()),
        }
        for h in horizons:
            col = f"D+{h}"
            vals = pd.to_numeric(g[col], errors="coerce").dropna()
            row[f"avg_{col}"] = float(vals.mean()) if len(vals) else np.nan
            row[f"median_{col}"] = float(vals.median()) if len(vals) else np.nan
            row[f"win_rate_{col}"] = float((vals > 0).mean()) if len(vals) else np.nan
        mfe_col = f"MFE_D+{forward_bars}"
        mae_col = f"MAE_D+{forward_bars}"
        row[f"avg_{mfe_col}"] = float(pd.to_numeric(g[mfe_col], errors="coerce").mean())
        row[f"avg_{mae_col}"] = float(pd.to_numeric(g[mae_col], errors="coerce").mean())
        rows.append(row)

    out = pd.DataFrame(rows)
    out["_label_order"] = out["long_quality_label"].map(label_order).fillna(99)
    return out.sort_values(["_label_order", "stage"]).drop(columns="_label_order").reset_index(drop=True)


def _write_excel(
    path: Path,
    events: pd.DataFrame,
    summary: pd.DataFrame,
    long_v2_summary: pd.DataFrame,
    long_candidates: pd.DataFrame,
    universe: pd.DataFrame,
    errors: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        long_v2_summary.to_excel(writer, sheet_name="LongV2Summary", index=False)
        long_candidates.to_excel(writer, sheet_name="LongCandidates", index=False)
        events.to_excel(writer, sheet_name="Events", index=False)
        universe.to_excel(writer, sheet_name="Universe", index=False)
        errors.to_excel(writer, sheet_name="Errors", index=False)


def _load_market_feature_map(
    universe: pd.DataFrame,
    history_start: str,
    forward_end: str,
) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    feature_map: dict[str, pd.DataFrame] = {}
    errors: list[dict] = []

    markets = sorted({str(x).upper() for x in universe.get("market", pd.Series(dtype=str)).dropna()})
    for market in markets:
        proxy = BENCHMARK_PROXY.get(market)
        if not proxy:
            errors.append({
                "ticker": f"BENCHMARK:{market}",
                "name": "",
                "error": f"No LONG V2 benchmark proxy configured for market={market}",
            })
            continue
        try:
            raw = _normalize_ohlcv(load_pykrx(proxy, history_start, forward_end))
            feature_map[market] = prepare_market_features(raw)
            print(f"[V2] Market proxy {market}: {proxy} ({len(raw):,} bars)")
        except Exception as exc:
            errors.append({
                "ticker": f"BENCHMARK:{market}",
                "name": proxy,
                "error": repr(exc),
            })
            print(f"[WARN] LONG V2 market proxy failed {market}/{proxy}: {exc}")
    return feature_map, errors


def run_range(args) -> int:
    start, end = v1.parse_date_range(args.date_range)
    params = v1.RangeParams(
        start=start,
        end=end,
        top_n=args.top_n,
        sort_by=args.sort_by,
        forward_bars=args.forward_bars,
        history_days=args.history_days,
        capital=args.capital,
        use_risk_cap=args.risk_cap,
        use_stop=not args.no_stop,
        include_dynamic_rsi=args.dynamic_rsi,
    )

    stock = v1._import_pykrx()
    snapshot = _latest_market_date(stock, end)
    universe = _get_universe(snapshot, params.top_n, params.sort_by)

    history_start = (start - pd.Timedelta(days=params.history_days)).strftime("%Y%m%d")
    forward_end = (end + pd.Timedelta(days=max(120, params.forward_bars * 3))).strftime("%Y%m%d")

    market_feature_map, benchmark_errors = _load_market_feature_map(
        universe,
        history_start,
        forward_end,
    )

    cfg = StrategyConfig(
        total_capital=params.capital,
        use_two_percent_risk_cap=params.use_risk_cap,
        use_protective_stop=params.use_stop,
    )
    analyzer = DynamicChartAnalyzer(cfg, include_dynamic_rsi=params.include_dynamic_rsi)

    print("=" * 78)
    print("DynamicChartAnalyzer Range Backtest V2 - LONG quality research")
    print("=" * 78)
    print(f"Date range       : {start:%Y%m%d}~{end:%Y%m%d}")
    print(f"Universe snapshot: {snapshot}")
    print(f"Universe TOP N   : {len(universe)}")
    print(f"Sort by          : {params.sort_by}")
    print(f"Forward bars     : {params.forward_bars}")
    print(f"Capital          : {params.capital:,.0f} KRW (Stage 1/2/3 = 1:2:7 unchanged)")
    print(f"V2 labels        : CONFIRMED >= {args.v2_confirmed_score:g}, WATCH >= {args.v2_watch_score:g}")
    print("V2 ranking       : Quality score desc, then source rank")
    print("Benchmark proxy  : KOSPI=069500 / KOSDAQ=229200 (per-ticker OHLCV)")
    print()

    event_rows: list[dict] = []
    error_rows: list[dict] = list(benchmark_errors)
    rs_panel_rows: list[pd.DataFrame] = []

    for n, rec in enumerate(universe.itertuples(index=False), start=1):
        ticker = str(rec.ticker).zfill(6)
        name = str(rec.name or "")
        market = str(getattr(rec, "market", "") or "").upper()
        print(f"[{n:03d}/{len(universe):03d}] {ticker} {name}")
        try:
            raw = _normalize_ohlcv(load_pykrx(ticker, history_start, forward_end))
            analyzed, events = analyzer.analyze(raw)
            enriched = add_long_v2_features(analyzed, market_feature_map.get(market))

            panel_slice = enriched.loc[
                (enriched.index >= start) & (enriched.index <= end),
                ["rs_20", "rs_60"],
            ].copy()
            if not panel_slice.empty:
                panel_slice = panel_slice.reset_index()
                first_col = panel_slice.columns[0]
                panel_slice = panel_slice.rename(columns={first_col: "signal_date"})
                panel_slice["ticker"] = ticker
                rs_panel_rows.append(panel_slice[["signal_date", "ticker", "rs_20", "rs_60"]])

            if events.empty:
                continue

            e = events.copy()
            e["date"] = pd.to_datetime(e["date"])
            e = e[(e["date"] >= start) & (e["date"] <= end)]
            e = e[e["action"].astype(str).str.contains("_ENTRY_STAGE_", regex=False)]
            if e.empty:
                continue

            for _, row in e.iterrows():
                action = str(row["action"])
                side = "SHORT" if action.startswith("SHORT_") else "LONG"
                signal_date = pd.Timestamp(row["date"])
                feature_row = enriched.loc[signal_date]

                base = {
                    "signal_date": signal_date,
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "source_rank": int(rec.source_rank),
                    "sort_by": params.sort_by,
                    "side": side,
                    "direction": _direction(action),
                    "stage": int(row.get("stage", 0)),
                    "action": action,
                    "entry_price": float(row["price"]),
                    "entry_amount_krw": float(row.get("amount_krw", np.nan)),
                    "cumulative_invested_krw": float(row.get("cumulative_invested_krw", np.nan)),
                    "weighted_entry_price": float(row.get("weighted_entry_price", np.nan)),
                    "stop_price": row.get("stop_price", np.nan),
                    "reference_target_price": row.get("reference_target_price", np.nan),
                    "risk_capped": bool(row.get("risk_capped", False)),
                }
                for col in BASE_EVENT_FEATURE_COLUMNS:
                    base[col] = _scalar(feature_row.get(col, np.nan))

                event_rows.append(_add_forward_metrics(base, raw, params.forward_bars))
        except Exception as exc:
            error_rows.append({"ticker": ticker, "name": name, "error": repr(exc)})
            print(f"  [WARN] {exc}")
        time.sleep(max(0.0, float(args.request_delay)))

    events_df = pd.DataFrame(event_rows)

    # Percentiles are computed across every successfully loaded universe stock on
    # each date, not merely across stocks that happened to emit a LONG signal.
    if rs_panel_rows:
        rs_panel = pd.concat(rs_panel_rows, ignore_index=True)
        rs_panel = add_rs_percentiles(rs_panel)
        rs_lookup = rs_panel[
            ["signal_date", "ticker", "rs_percentile_20", "rs_percentile_60"]
        ].drop_duplicates(["signal_date", "ticker"], keep="last")
    else:
        rs_lookup = pd.DataFrame(
            columns=["signal_date", "ticker", "rs_percentile_20", "rs_percentile_60"]
        )

    if not events_df.empty:
        events_df["signal_date"] = pd.to_datetime(events_df["signal_date"])
        events_df = events_df.merge(
            rs_lookup,
            on=["signal_date", "ticker"],
            how="left",
            validate="many_to_one",
        )
        events_df = score_long_events(
            events_df,
            confirmed_score=float(args.v2_confirmed_score),
            watch_score=float(args.v2_watch_score),
        )
        events_df = events_df.sort_values(["signal_date", "ticker", "stage"]).reset_index(drop=True)
        events_df["daily_stage_rank"] = (
            events_df.groupby(["signal_date", "side", "stage"])["source_rank"]
            .rank(method="first")
            .astype(int)
        )
        events_df["is_daily_top5_long"] = (
            events_df["side"].eq("LONG")
            & events_df["long_quality_label"].isin(["CONFIRMED", "WATCH"])
            & pd.to_numeric(events_df["daily_long_rank"], errors="coerce").le(5)
        )
    else:
        for col in [
            "rs_percentile_20",
            "rs_percentile_60",
            "long_quality_score",
            "long_quality_label",
            "daily_long_rank",
            "daily_stage_rank",
            "is_daily_top5_long",
        ]:
            events_df[col] = pd.Series(dtype=float if "score" in col or "percentile" in col else object)

    summary_df = _build_summary(events_df, params.forward_bars)
    long_v2_summary_df = _build_long_v2_summary(events_df, params.forward_bars)
    errors_df = pd.DataFrame(error_rows, columns=["ticker", "name", "error"])

    long_mask = events_df["side"].eq("LONG") if "side" in events_df.columns else pd.Series(False, index=events_df.index)
    quality_mask = (
        events_df["long_quality_label"].isin(["CONFIRMED", "WATCH"])
        if "long_quality_label" in events_df.columns
        else pd.Series(False, index=events_df.index)
    )
    long_candidates_df = events_df[long_mask & quality_mask].copy()
    if not long_candidates_df.empty:
        long_candidates_df = long_candidates_df.sort_values(
            ["signal_date", "daily_long_rank", "stage"],
            ascending=[True, True, False],
        )

    out_dir = Path(args.output_root) / f"range_{start:%Y%m%d}_{end:%Y%m%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "dynamic_range_events.csv"
    summary_path = out_dir / "dynamic_range_summary.csv"
    v2_summary_path = out_dir / "dynamic_long_v2_summary.csv"
    candidates_path = out_dir / "dynamic_long_v2_candidates.csv"
    universe_path = out_dir / "universe.csv"
    errors_path = out_dir / "errors.csv"
    excel_path = out_dir / "dynamic_range_backtest.xlsx"

    events_df.to_csv(events_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    long_v2_summary_df.to_csv(v2_summary_path, index=False, encoding="utf-8-sig")
    long_candidates_df.to_csv(candidates_path, index=False, encoding="utf-8-sig")
    universe.to_csv(universe_path, index=False, encoding="utf-8-sig")
    errors_df.to_csv(errors_path, index=False, encoding="utf-8-sig")
    _write_excel(
        excel_path,
        events_df,
        summary_df,
        long_v2_summary_df,
        long_candidates_df,
        universe,
        errors_df,
    )

    print()
    print("=" * 78)
    print("Range backtest V2 finished")
    print("=" * 78)
    print(f"Entry events     : {len(events_df):,}")
    print(f"LONG events      : {int(events_df['side'].eq('LONG').sum()) if not events_df.empty else 0:,}")
    if not events_df.empty:
        labels = events_df.loc[events_df["side"].eq("LONG"), "long_quality_label"].value_counts()
        print(
            "LONG V2 labels   : "
            + " / ".join(f"{k}={int(labels.get(k, 0))}" for k in ["CONFIRMED", "WATCH", "REJECT"])
        )
    print(f"Errors           : {len(errors_df):,}")
    print(f"Saved            : {excel_path}")
    print(f"Saved            : {events_path}")
    print(f"Saved            : {v2_summary_path}")
    print(f"Saved            : {candidates_path}")
    return 0


def build_parser():
    p = v1.build_parser()
    p.description = "DynamicChartAnalyzer TOP-N range backtest V2 (LONG quality research)"
    p.add_argument(
        "--v2-confirmed-score",
        type=float,
        default=70.0,
        help="LONG V2 CONFIRMED threshold; default 70",
    )
    p.add_argument(
        "--v2-watch-score",
        type=float,
        default=55.0,
        help="LONG V2 WATCH threshold; default 55",
    )
    return p


if __name__ == "__main__":
    raise SystemExit(run_range(build_parser().parse_args()))
