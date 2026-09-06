# MaterialBacktester V1

Input:

```text
MaterialAnalyzer/data/history/material_history_backtest.csv
```

Run:

```bat
MaterialAnalyzer\run_material_backtest.bat
```

The backtester uses the close of `market_date` as the entry price and never silently shifts a missing entry to a later date.

Forward horizons:

```text
D+1 / D+5 / D+10 / D+20 / D+40 / D+60
```

Outputs:

```text
MaterialAnalyzer/data/history/backtest/material_backtest_results.csv
MaterialAnalyzer/data/history/backtest/material_backtest_summary.csv
MaterialAnalyzer/data/history/backtest/material_backtest_errors.csv
```

`material_backtest_results.csv` contains raw forward return, absolute move, and directional return for POSITIVE/NEGATIVE events. NEUTRAL events intentionally have no directional return.

`material_backtest_summary.csv` aggregates by:

```text
OVERALL
material_status
material_score_band
ticker_material_score_band
positive_negative
event_type
event_stage
novelty_status
relation_type
source_id
theme
```

For every horizon it reports:

```text
complete count
average raw return
median raw return
raw win rate
average absolute move
directional count
average directional return
directional hit rate
```

Material Score is an importance/certainty score rather than a bullish score, so `avg_abs_D+N` is a core metric. Directional hit rate is evaluated only where `positive_negative` is POSITIVE or NEGATIVE.
