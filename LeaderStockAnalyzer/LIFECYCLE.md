# Leader Lifecycle V1

`LeaderLifecycleEngine` tracks how a stock's leadership evolves across scan dates.
It is intentionally independent from the existing Leader Score and confirmation rules in V1.

## State flow

```text
DISCOVERY
  -> EMERGING
  -> LEADER
  -> PERSISTENT_LEADER
  -> EXHAUSTING
  -> BROKEN
```

A recovered `BROKEN` stock re-enters through `EMERGING` instead of jumping directly back to `LEADER`.

## State meaning

- `DISCOVERY`: early leadership candidate, but leadership evidence is not strong enough yet.
- `EMERGING`: strong current Leader Score/rank, but recent persistence is still limited.
- `LEADER`: Leader Score/rank and recent persistence are both established.
- `PERSISTENT_LEADER`: leadership has remained strong for several recent trading days.
- `EXHAUSTING`: a previously established leader is showing multiple degradation signals.
- `BROKEN`: leadership structure has materially broken or an exhausting leader has broken down further.

## V1 evidence

Lifecycle V1 reuses existing analyzer evidence instead of adding a new score:

- Leader Score
- market leader rank
- PersistenceEngine score/level
- recent TOP20 trading-value days
- breakout exhaustion flag
- false-breakout flag
- chase risk
- 20-day drawdown
- MA10/MA20 break context

The dedicated `Exhaustion Risk` feature is planned separately. V1 uses only simple degradation flags so lifecycle can be validated first.

## Output columns

Range and screen results include:

- `lifecycle_available`
- `lifecycle_state`
- `lifecycle_prev_state`
- `lifecycle_transition`
- `lifecycle_days_in_state`
- `lifecycle_observed_days`
- `lifecycle_state_start_date`
- `lifecycle_reason`
- `lifecycle_drawdown_20d_pct`
- `lifecycle_below_ma20`
- `lifecycle_exhaustion_flags`
- `lifecycle_broken_flags`

Range analysis also writes:

```text
results/range_YYYYMMDD_YYYYMMDD/lifecycle_transitions.csv
```

This file contains only rows whose lifecycle state changed while the stock was observed in the daily Leader universe.

## Important V1 rule

Lifecycle does **not** modify:

- Leader Score
- Timing Score
- STRONG_CONFIRMED / CONFIRMED / WATCH / REJECT

This is deliberate. First compare forward returns by lifecycle state. Only after the state labels show predictive value should lifecycle be promoted into confirmation gates or position sizing.

## Test

From `LeaderStockAnalyzer`:

```bash
python -m pytest tests/test_lifecycle.py -q
```

## Next validation

Recommended first validation from range results:

- average/median D+5, D+20, D+60 by lifecycle state
- MFE/MAE by lifecycle state
- `EMERGING -> LEADER` transition performance
- `LEADER -> PERSISTENT_LEADER` transition performance
- `LEADER/PERSISTENT_LEADER -> EXHAUSTING` post-transition drawdown
- `EXHAUSTING -> BROKEN` failure rate

These results should drive V2 threshold changes rather than tuning the state thresholds by intuition alone.
