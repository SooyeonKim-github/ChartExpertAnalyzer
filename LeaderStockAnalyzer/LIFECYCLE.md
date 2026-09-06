# Leader Lifecycle V2.2

`LeaderLifecycleEngine` tracks how a stock's leadership evolves across scan dates while remaining independent from the existing Leader Score confirmation rules.

## State flow

```text
DISCOVERY
  -> EMERGING
  -> LEADER
  -> PERSISTENT_LEADER
  -> EXHAUSTING
  -> BROKEN
```

A recovered `BROKEN` stock re-enters through `EMERGING`.
The first observed date may infer a mature state directly when historical persistence already proves it. After initialization, normal upward transitions move one stage at a time.

## V2 structural rules

Leader Score collapse alone never means `BROKEN`.

`BROKEN` requires structural price failure such as:

- deep 20-day drawdown while below MA20
- MA20 break with a large negative daily return
- false breakout while below MA20

Established leaders pass through `EXHAUSTING` before `BROKEN`.

Default hysteresis:

```text
promotion_confirm_days = 2
demotion_confirm_days  = 2
recovery_confirm_days  = 2
```

## V2.2 Emerging Leader integration

When `EmergingLeaderEngine` data is available, `DISCOVERY -> EMERGING` is no longer driven by current Leader Score/rank alone.

Normal promotion requires:

- lifecycle Leader Score/rank activation conditions
- `true_emerging_flag = true`
- two-session promotion confirmation by default

`true_emerging_flag` comes from Emerging Leader V1.1, which uses:

```text
Rank Velocity               50
Trading-value Acceleration  25
Relative-strength Accel.    15
Freshness                   10
- Overheat Penalty
```

Late momentum spikes are labeled `MOMENTUM_SPIKE` and cannot activate `true_emerging_flag`.

Default behavior also disables one-observation fast-track:

```text
allow_strong_emerging_fast_track = false
```

So even a high-quality `STRONG_EMERGING` candidate normally needs repeated confirmation. Fast-track remains available only as an explicit experiment setting.

Once a stock has entered `EMERGING`, Rank Velocity is allowed to cool. Promotion to `LEADER` is based on established Leader Score/rank/persistence evidence. This avoids penalizing a successful emerging leader simply because its rank has already reached the top of the market.

See `EMERGING_LEADER.md` for detailed formulas and output columns.

## Output

Range and screen results include lifecycle columns such as:

- `lifecycle_state`
- `lifecycle_prev_state`
- `lifecycle_transition`
- `lifecycle_days_in_state`
- `lifecycle_reason`
- `lifecycle_drawdown_20d_pct`
- `lifecycle_exhaustion_flags`
- `lifecycle_broken_flags`

Range analysis writes:

```text
lifecycle_transitions.csv
emerging_events.csv
emerging_summary.csv
```

`emerging_events.csv` contains only lifecycle episode starts and labels each event cohort.
`emerging_summary.csv` separates `INITIAL_INFERENCE` from `RANK_VELOCITY_CONFIRMED` so Rank Velocity performance can be measured without mixing in mature initial-state inference.

## Decision-rule isolation

Lifecycle still does not modify:

- Leader Score
- Timing Score
- STRONG_CONFIRMED / CONFIRMED / WATCH / REJECT

This preserves clean backtest attribution before lifecycle information is promoted into confirmation gates or position sizing.

## Test

From `LeaderStockAnalyzer`:

```bash
python -m pytest tests/test_lifecycle.py tests/test_emerging.py -q
```
