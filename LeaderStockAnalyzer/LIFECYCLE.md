# Leader Lifecycle V2

`LeaderLifecycleEngine` tracks how a stock's leadership evolves across scan dates.
Lifecycle remains independent from the existing Leader Score and confirmation rules so its predictive value can be validated first.

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
The first observed date may infer `LEADER` or `PERSISTENT_LEADER` directly when recent historical persistence already proves that state. After initialization, normal upward transitions move one stage at a time.

## V2 changes

Lifecycle V2 was tuned after the first range result showed too many `EMERGING -> BROKEN` transitions caused by `leader_score_collapse` alone.

### 1. Leader Score collapse no longer means BROKEN

A low Leader Score is treated as weakening evidence, not structural failure.

- `EMERGING` weakness must persist for `demotion_confirm_days` before returning to `DISCOVERY`.
- `LEADER` weakness must persist before returning to `EMERGING`.
- `PERSISTENT_LEADER` persistence decay must persist before returning to `LEADER`.

### 2. BROKEN requires structural price failure

`BROKEN` evidence is now limited to strong price-structure failures:

- 20-day drawdown beyond the configured threshold **and** price below MA20
- price below MA20 with a large negative daily return
- false breakout while price is below MA20

An established `LEADER` or `PERSISTENT_LEADER` with structural failure first moves to `EXHAUSTING`. If the structural failure remains while `EXHAUSTING`, it moves to `BROKEN`.

### 3. EXHAUSTING is used before failure

Exhaustion evidence includes:

- breakout exhaustion
- false breakout
- high chase risk
- meaningful 20-day drawdown
- weak close below MA10
- Leader Score weakness for an established leader
- Persistence Score decay for an established leader

At least `exhausting_min_flags` signals are required unless a hard structural break is already detected.

### 4. Hysteresis

One-day noise should not constantly change lifecycle state.

Default confirmation settings:

```text
promotion_confirm_days = 2
demotion_confirm_days  = 2
recovery_confirm_days  = 2
```

Normal promotion therefore behaves like:

```text
DISCOVERY --confirmed--> EMERGING --confirmed--> LEADER --confirmed--> PERSISTENT_LEADER
```

`PERSISTENT_LEADER` also requires sufficient persistence evidence and either enough days as `LEADER` or a HIGH persistence level.

### 5. Memory reset

If a ticker disappears from the observed Leader universe for longer than `memory_reset_calendar_days`, lifecycle memory resets and the next observation is treated as a new initial inference.

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

## Decision-rule isolation

Lifecycle V2 still does **not** modify:

- Leader Score
- Timing Score
- STRONG_CONFIRMED / CONFIRMED / WATCH / REJECT

This lets forward returns by lifecycle state be measured before lifecycle becomes part of confirmation gates or position sizing.

## Test

From `LeaderStockAnalyzer`:

```bash
python -m pytest tests/test_lifecycle.py -q
```

The tests cover:

- initial mature-state inference
- one-stage promotion with confirmation
- Leader Score collapse not causing BROKEN
- structural failure routing through EXHAUSTING
- degradation-based EXHAUSTING detection
- days-in-state tracking

## Next validation

Re-run the same historical range and compare V1 vs V2:

- `EMERGING -> BROKEN` count should fall sharply
- `EXHAUSTING` should appear before meaningful `BROKEN` events
- `DISCOVERY -> LEADER/PERSISTENT_LEADER` skips should disappear after initial observation
- `BROKEN` forward returns should be materially worse than `LEADER/PERSISTENT_LEADER`
- `EXHAUSTING` should show weaker MFE / worse MAE than healthy leader states
