from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dynamic_chart_analyzer import DynamicChartAnalyzer, StrategyConfig, build_entry_plan
from us_market.provider import USYFinanceProvider


def parse_args():
    p = argparse.ArgumentParser(description="DynamicChartAnalyzer for a US stock ticker")
    p.add_argument("--ticker", required=True, help="US ticker, e.g. AAPL, NVDA, MSFT")
    p.add_argument("--start", default="20250101", help="YYYYMMDD")
    p.add_argument("--end", default="20261231", help="YYYYMMDD")
    p.add_argument("--capital", type=float, default=10_000_000, help="Capital base; allocation ratios remain 1:2:7")
    p.add_argument("--risk-cap", action="store_true", help="Enable optional account 2%% risk cap")
    p.add_argument("--no-stop", action="store_true", help="Disable protective swing stop")
    p.add_argument("--dynamic-rsi", action="store_true", help="Add experimental Dynamic RSI approximation")
    p.add_argument("--out", default="results_us", help="Output directory")
    return p.parse_args()


def main():
    args = parse_args()
    ticker = args.ticker.strip().upper()
    cfg = StrategyConfig(
        total_capital=args.capital,
        use_two_percent_risk_cap=args.risk_cap,
        use_protective_stop=not args.no_stop,
    )
    plan = build_entry_plan(cfg)

    provider = USYFinanceProvider()
    df = provider.get_ohlcv_by_date(ticker, args.start, args.end)
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
    })[["open", "high", "low", "close", "volume"]]

    analyzer = DynamicChartAnalyzer(cfg, include_dynamic_rsi=args.dynamic_rsi)
    analyzed, events = analyzer.analyze(df)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    analyzed_path = out_dir / f"{ticker}_analysis.csv"
    events_path = out_dir / f"{ticker}_events.csv"
    analyzed.to_csv(analyzed_path, encoding="utf-8-sig")
    events.to_csv(events_path, index=False, encoding="utf-8-sig")

    print("=" * 72)
    print(f"DynamicChartAnalyzer US - {ticker}")
    print("=" * 72)
    print(f"Capital : {plan.capital_base:,.0f}")
    print(f"Stage 1 : {plan.stage1_amount:,.0f} (10%)")
    print(f"Stage 2 : {plan.stage2_amount:,.0f} (20%)")
    print(f"Stage 3 : {plan.stage3_amount:,.0f} (70%)")
    print("\nLatest signal summary")
    for key, value in analyzer.latest_summary(analyzed).items():
        print(f"  {key}: {value}")
    print(f"\nSaved: {analyzed_path}")
    print(f"Saved: {events_path}")


if __name__ == "__main__":
    main()
