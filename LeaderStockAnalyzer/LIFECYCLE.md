# Leader Lifecycle V2.1

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

## V2.1 Emerging Leader integration

When `EmergingLeaderEngine` data is available, `DISCOVERY -> EMERGING` is no longer driven by current Leader Score/rank alone.

Normal promotion requires:

- lifecycle Leader Score/rank activation conditions
- `true_emerging_flag = true`
- configured promotion confirmation

`true_emerging_flag` comes from the independent Emerging Leader Score:

```text
Rank Velocity               50
Trading-value Acceleration  25
Relative-strength Accel.    15
Freshness                   10
```

A `STRONG_EMERGING` stock can fast-track `DISCOVERY -> EMERGING` when it also satisfies the strong current-rank and 5-day Rank Velocity requirements.

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

`emerging_events.csv` is deduplicated to lifecycle episode starts so the same multi-day EMERGING episode is not counted repeatedly.

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
