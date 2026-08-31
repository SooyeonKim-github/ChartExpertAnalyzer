from __future__ import annotations

import argparse
from pathlib import Path

from dynamic_chart_analyzer import DynamicChartAnalyzer, StrategyConfig, build_entry_plan
from dynamic_chart_analyzer.providers import load_csv, load_pykrx


def parse_args():
    p = argparse.ArgumentParser(description="RSI + MACD + Ichimoku 1:2:7 staged chart analyzer")
    source = p.add_mutually_exclusive_group(required=False)
    source.add_argument("--csv", help="OHLCV CSV path")
    source.add_argument("--ticker", help="KRX ticker, e.g. 005930")
    p.add_argument("--start", default="20250101", help="YYYYMMDD; used with --ticker")
    p.add_argument("--end", default="20261231", help="YYYYMMDD; used with --ticker")
    p.add_argument("--capital", type=float, default=10_000_000, help="Capital base in KRW")
    p.add_argument("--risk-cap", action="store_true", help="Enable optional account 2%% risk cap using the Stage-1 swing stop")
    p.add_argument("--no-stop", action="store_true", help="Disable protective swing stop")
    p.add_argument("--dynamic-rsi", action="store_true", help="Add experimental Dynamic RSI approximation (reporting only)")
    p.add_argument("--out", default="results", help="Output directory")
    p.add_argument("--show-plan", action="store_true", help="Print base 1:2:7 allocation plan and exit")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = StrategyConfig(
        total_capital=args.capital,
        use_two_percent_risk_cap=args.risk_cap,
        use_protective_stop=not args.no_stop,
    )
    plan = build_entry_plan(cfg)

    print("=" * 72)
    print("DynamicChartAnalyzer - RSI / MACD / Ichimoku staged 1:2:7")
    print("=" * 72)
    print(f"Capital : {plan.capital_base:,.0f} KRW")
    print(f"Stage 1 : {plan.stage1_amount:,.0f} KRW (10%) - RSI extreme-zone exit")
    print(f"Stage 2 : {plan.stage2_amount:,.0f} KRW (20%) - MACD confirmation")
    print(f"Stage 3 : {plan.stage3_amount:,.0f} KRW (70%) - Ichimoku trend confirmation")
    print(f"Protective stop : {'ON' if cfg.use_protective_stop else 'OFF'}")
    print(f"2% account-risk cap : {'ON' if cfg.use_two_percent_risk_cap else 'OFF'}")
    if cfg.use_two_percent_risk_cap:
        print("  Actual 1:2:7 amounts are calculated at Stage 1 after the swing-stop distance is known.")

    if args.show_plan and not args.csv and not args.ticker:
        return

    if args.csv:
        df = load_csv(args.csv)
        tag = Path(args.csv).stem
    elif args.ticker:
        df = load_pykrx(args.ticker, args.start, args.end)
        tag = args.ticker
    else:
        print("\nNo data source supplied. Use --csv or --ticker, or --show-plan for allocation only.")
        return

    analyzer = DynamicChartAnalyzer(cfg, include_dynamic_rsi=args.dynamic_rsi)
    analyzed, events = analyzer.analyze(df)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    analyzed_path = out_dir / f"{tag}_analysis.csv"
    events_path = out_dir / f"{tag}_events.csv"
    analyzed.to_csv(analyzed_path, encoding="utf-8-sig")
    events.to_csv(events_path, index=False, encoding="utf-8-sig")

    print("\nLatest signal summary")
    for k, v in analyzer.latest_summary(analyzed).items():
        print(f"  {k}: {v}")
    print(f"\nSaved: {analyzed_path}")
    print(f"Saved: {events_path}")


if __name__ == "__main__":
    main()
