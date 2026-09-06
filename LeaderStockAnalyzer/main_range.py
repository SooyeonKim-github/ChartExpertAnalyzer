from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from leader_stock_analyzer import load_config, screen_date
from leader_stock_analyzer.data_provider import PyKrxLeaderDataProvider
from leader_stock_analyzer.emerging_reporting import EmergingTransitionAnalyzerV12
from leader_stock_analyzer.exhaustion import ExhaustionTransitionAnalyzer
from leader_stock_analyzer.lifecycle import LeaderLifecycleEngine
from leader_stock_analyzer.performance import ForwardPerformanceEngine, PerformanceAttributionEngine


def _parse_range(value: str) -> tuple[str, str]:
    if "~" not in value:
        raise argparse.ArgumentTypeError("Use YYYYMMDD~YYYYMMDD")
    start, end = value.split("~", 1)
    pd.Timestamp(start)
    pd.Timestamp(end)
    return start, end


def main() -> None:
    p = argparse.ArgumentParser(description="LeaderStockAnalyzer range scan")
    p.add_argument("--date-range", required=True, type=_parse_range)
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--out", default="results")
    args = p.parse_args()
    start, end = args.date_range

    base_dir = Path(__file__).resolve().parent
    cfg = load_config(base_dir / args.config)
    provider = PyKrxLeaderDataProvider(cfg, base_dir)
    lifecycle = LeaderLifecycleEngine(cfg)
    performance = ForwardPerformanceEngine(cfg)
    attribution = PerformanceAttributionEngine(cfg)
    emerging_report = EmergingTransitionAnalyzerV12(cfg)
    exhaustion_report = ExhaustionTransitionAnalyzer(cfg)

    provider.prepare_range(start, end, args.top_n)
    dates = provider.get_trading_dates(start, end)
    rows: list[dict] = []

    print(
        f"[INFO] Leader range ready | trading_days={len(dates)} "
        f"| daily ranking=scan-date trading_value TOP {args.top_n}"
    )
    print(
        "[INFO] Emerging Leader V1.1 enabled | score=Rank50 + Money25 + RS15 + Freshness10 "
        "| overheat penalty=ON | max_chase=40"
    )
    print(
        "[INFO] Leader Lifecycle V2.4 enabled | Emerging activation=Rank Velocity x2 "
        "| hold=LeaderScore>=60 & Rank<=50 | Leader Core evidence=2 hits / 10 observations "
        "| fast-track=OFF | BROKEN requires structural price failure"
    )
    print(
        "[INFO] Exhaustion Risk V1 enabled | Overextension25 + Deceleration25 + "
        "Distribution20 + MoneyDecay15 + Structure15 | observational_only=ON"
    )

    max_horizon = max(performance.horizons + performance.excursion_horizons)
    future_calendar_days = max_horizon * 2 + 30
    range_calendar_days = max(0, (pd.Timestamp(end) - pd.Timestamp(start)).days)
    full_series_future_days = range_calendar_days + future_calendar_days
    forward_cache: dict[str, pd.DataFrame] = {}

    for i, d in enumerate(dates, start=1):
        print(f"\n[{i}/{len(dates)}] {d}")
        _, results = screen_date(
            cfg,
            scan_date=d,
            top_n=args.top_n,
            base_dir=base_dir,
            progress=False,
            provider=provider,
            lifecycle_engine=lifecycle,
        )
        for r in results:
            rec = r.to_dict()
            ticker = str(r.ticker).zfill(6)
            try:
                if ticker not in forward_cache:
                    forward_cache[ticker] = provider.get_daily(
                        ticker,
                        start,
                        future_days=full_series_future_days,
                    )
                rec.update(
                    performance.evaluate(
                        forward_cache[ticker],
                        d,
                        breakout_reference=r.breakout_reference,
                    )
                )
            except Exception as exc:
                print(f"[WARN] forward performance {d} {ticker} {r.name}: {exc}")
                rec.update(
                    performance.evaluate(
                        pd.DataFrame(),
                        d,
                        breakout_reference=r.breakout_reference,
                    )
                )
            rows.append(rec)

    df = pd.DataFrame(rows)
    out_dir = base_dir / args.out / f"range_{start}_{end}"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_path = out_dir / "range_all_results.csv"
    cand_path = out_dir / "range_candidates.csv"
    lifecycle_path = out_dir / "lifecycle_transitions.csv"
    emerging_events_path = out_dir / "emerging_events.csv"
    emerging_summary_path = out_dir / "emerging_summary.csv"
    exhaustion_events_path = out_dir / "exhaustion_events.csv"
    exhaustion_summary_path = out_dir / "exhaustion_summary.csv"

    df.to_csv(all_path, index=False, encoding="utf-8-sig")
    if not df.empty:
        df[df["status"].isin(["STRONG_CONFIRMED", "CONFIRMED"])].to_csv(
            cand_path,
            index=False,
            encoding="utf-8-sig",
        )
        transitions = df[df["lifecycle_transition"].fillna(False)].copy()
        transitions.to_csv(lifecycle_path, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(cand_path, index=False, encoding="utf-8-sig")
        df.to_csv(lifecycle_path, index=False, encoding="utf-8-sig")

    emerging_events = emerging_report.events(df)
    emerging_summary = emerging_report.summary(emerging_events)
    emerging_events.to_csv(emerging_events_path, index=False, encoding="utf-8-sig")
    emerging_summary.to_csv(emerging_summary_path, index=False, encoding="utf-8-sig")

    exhaustion_events = exhaustion_report.events(df)
    exhaustion_summary = exhaustion_report.summary(exhaustion_events)
    exhaustion_events.to_csv(exhaustion_events_path, index=False, encoding="utf-8-sig")
    exhaustion_summary.to_csv(exhaustion_summary_path, index=False, encoding="utf-8-sig")

    perf_dir = out_dir / "performance"
    report_paths = attribution.write_reports(df, perf_dir)

    print(f"\n[DONE] {all_path}")
    print(f"[DONE] {cand_path}")
    print(f"[DONE] {lifecycle_path}")
    print(f"[DONE] {emerging_events_path}")
    print(f"[DONE] {emerging_summary_path}")
    print(f"[DONE] {exhaustion_events_path}")
    print(f"[DONE] {exhaustion_summary_path}")
    print(f"[DONE] performance reports -> {perf_dir}")
    for name, path in report_paths.items():
        print(f"       {name}: {path.name}")

    if not df.empty and "emerging_label" in df.columns:
        counts = df["emerging_label"].value_counts()
        print("\n[EMERGING LEADER V1.1]")
        for label in (
            "STRONG_EMERGING",
            "EMERGING",
            "WATCH",
            "NOT_EMERGING",
            "MOMENTUM_SPIKE",
        ):
            print(f"  {label:<18} {int(counts.get(label, 0))}")
        print(f"  {'TRUE_EMERGING':<18} {int(df['true_emerging_flag'].fillna(False).sum())}")
        print(f"  {'MOMENTUM_SPIKE':<18} {int(df['momentum_spike_flag'].fillna(False).sum())}")
        print(f"  {'EVENTS':<18} {len(emerging_events)}")
        if not emerging_summary.empty:
            print("\n[EMERGING COHORT SUMMARY]")
            for _, row in emerging_summary.iterrows():
                cohort = row.get("cohort", "UNKNOWN")
                count = int(row.get("event_count", 0))
                leader10 = row.get("leader_within_10d_rate", "-")
                reversion5 = row.get("lifecycle_reversion_within_5d_rate", "-")
                price_fail20 = row.get("price_failure_D20_rate", "-")
                avg20 = row.get("avg_D+20", "-")
                print(
                    f"  {cohort:<26} count={count:<4} "
                    f"leader10={leader10} reversion5={reversion5} "
                    f"priceFail20={price_fail20} avgD20={avg20}"
                )

    if not df.empty and "exhaustion_risk_label" in df.columns:
        counts = df["exhaustion_risk_label"].value_counts()
        print("\n[EXHAUSTION RISK V1]")
        for label in ("LOW", "WATCH", "HIGH", "CRITICAL"):
            print(f"  {label:<18} {int(counts.get(label, 0))}")
        print(f"  {'EVENTS':<18} {len(exhaustion_events)}")
        if not exhaustion_summary.empty:
            print("\n[EXHAUSTION COHORT SUMMARY]")
            for _, row in exhaustion_summary.iterrows():
                cohort = row.get("cohort", "UNKNOWN")
                count = int(row.get("event_count", 0))
                exhausting5 = row.get("exhausting_within_5d_rate", "-")
                broken10 = row.get("broken_within_10d_rate", "-")
                avg20 = row.get("avg_D+20", "-")
                mae20 = row.get("avg_MAE_D20", "-")
                print(
                    f"  {cohort:<12} count={count:<4} exhausting5={exhausting5} "
                    f"broken10={broken10} avgD20={avg20} avgMAE20={mae20}"
                )

    if not df.empty and "lifecycle_state" in df.columns:
        counts = df["lifecycle_state"].value_counts()
        print("\n[LIFECYCLE]")
        for state in (
            "DISCOVERY",
            "EMERGING",
            "LEADER",
            "PERSISTENT_LEADER",
            "EXHAUSTING",
            "BROKEN",
        ):
            print(f"  {state:<18} {int(counts.get(state, 0))}")


if __name__ == "__main__":
    main()
