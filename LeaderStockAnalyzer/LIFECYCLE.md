# Leader Lifecycle V2.3

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
Mature `LEADER` / `PERSISTENT_LEADER` evidence may still be inferred directly on first observation because persistence already contains prior-history evidence.

## Structural rules

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

## V2.3 Emerging Activation vs Hold

The V1.1 backtest showed that using fresh Rank Velocity for both activation and maintenance was too strict. A successful Emerging stock naturally loses rank velocity after reaching the top of the market.

V2.3 therefore separates two concepts.

### Emerging Activation

`DISCOVERY -> EMERGING` requires fresh Emerging Leader evidence:

```text
Leader Score >= 72
Market Leader Rank <= 20
true_emerging_flag = true
promotion confirmation = 2 observations by default
```

`true_emerging_flag` comes from Emerging Leader V1.1:

```text
Rank Velocity               50
Trading-value Acceleration  25
Relative-strength Accel.    15
Freshness                   10
- Overheat Penalty
```

`MOMENTUM_SPIKE` cannot activate Emerging.

### Emerging Hold

Once the stock is already `EMERGING`, fresh Rank Velocity is no longer required every day.

Default hold condition:

```text
Leader Score >= 60
AND
Market Leader Rank <= 50
```

If this hold condition remains true, the stock stays `EMERGING` even when `true_emerging_flag` becomes false.

If established Leader conditions are met for the configured confirmation period, it moves to:

```text
EMERGING -> LEADER
```

If the hold condition fails for `demotion_confirm_days`, it moves back to:

```text
EMERGING -> DISCOVERY
```

### Initial observation

A first observation that is only Emerging no longer bypasses confirmation.

Default behavior:

```text
initial_emerging_requires_confirmation = true
```

So:

```text
first Emerging observation
-> DISCOVERY / confirmation 1 of 2

second confirming observation
-> EMERGING
```

Direct first-observation `LEADER` / `PERSISTENT_LEADER` inference remains allowed when historical persistence already supports the mature state.

Fast-track remains disabled by default:

```text
allow_strong_emerging_fast_track = false
```

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

The primary V2.3 validation is whether `RANK_VELOCITY_CONFIRMED` events now have a higher `LEADER` conversion rate without reintroducing the large false-Emerging population from pre-overheat versions.

## Decision-rule isolation

Lifecycle still does not modify:

- Leader Score
- Timing Score
- STRONG_CONFIRMED / CONFIRMED / WATCH / REJECT

## Test

From `LeaderStockAnalyzer`:

```bash
python -m pytest tests/test_lifecycle.py tests/test_emerging.py -q
```
