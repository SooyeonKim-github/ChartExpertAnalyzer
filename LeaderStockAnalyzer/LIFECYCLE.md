# Leader Lifecycle V2.4

`LeaderLifecycleEngine` tracks how a stock's leadership evolves across scan dates while keeping Lifecycle independent from the existing confirmation status.

## State flow

```text
DISCOVERY
  -> EMERGING
  -> LEADER
  -> PERSISTENT_LEADER
  -> EXHAUSTING
  -> BROKEN
```

## Emerging activation

`DISCOVERY -> EMERGING` still requires fresh Rank Velocity evidence.

Default gate:

```text
Leader Score >= 72
Market Leader Rank <= 20
true_emerging_flag = true
promotion_confirm_days = 2
```

`MOMENTUM_SPIKE` cannot activate Emerging and strong fast-track remains disabled by default.

## Emerging hold

After activation, fresh Rank Velocity is no longer required every day.

```text
Leader Score >= 60
AND
Market Leader Rank <= 50
```

If the hold condition fails for `demotion_confirm_days`, the stock returns to `DISCOVERY`.

## V2.4 Emerging -> Leader evidence

The V2.3 range result showed that requiring Leader conditions on consecutive observations was too sensitive to daily Leader Score fluctuations.

V2.4 defines Leader Core Evidence as:

```text
Leader Score >= 75
AND
Market Leader Rank <= 20
```

While a stock is `EMERGING`, these hits are accumulated in a rolling observation window:

```text
leader_evidence_required = 2
leader_evidence_window_observations = 10
```

The hits do not need to be consecutive.

Example:

```text
Day 1  Leader Core O   evidence 1/2
Day 2  cooldown        evidence 1/2
Day 3  Leader Core O   evidence 2/2
       -> LEADER
```

This is intended to capture leaders that alternate between expansion and short consolidation rather than requiring two perfectly consecutive strong days.

Persistence is still evaluated at the next stage:

```text
LEADER -> PERSISTENT_LEADER
```

so Leader Core accumulation does not weaken the persistent-leader definition.

## Initial observation

An initial Emerging observation cannot bypass activation confirmation:

```text
initial_emerging_requires_confirmation = true
```

Mature `LEADER` / `PERSISTENT_LEADER` warm-start inference remains allowed when historical persistence already proves the mature state.

## Structural failure

Leader Score collapse alone never means `BROKEN`.

`BROKEN` requires structural price failure such as:

- deep 20-day drawdown while below MA20
- MA20 break with a large negative daily return
- false breakout while below MA20

Established leaders pass through `EXHAUSTING` before `BROKEN`.

## Emerging validation terminology

Range reporting now distinguishes lifecycle behavior from price outcome.

```text
lifecycle_reversion
= EMERGING returned to DISCOVERY before LEADER conversion

price_failure_D20
= D+20 return <= 0

strong_price_success_D20
= D+20 return >= +10%
```

The legacy `false_emerging_*` columns remain for backward compatibility, but `lifecycle_reversion_*` should be used for interpretation.

## Output

Range analysis writes:

```text
range_all_results.csv
range_candidates.csv
lifecycle_transitions.csv
emerging_events.csv
emerging_summary.csv
```

## Tests

From `LeaderStockAnalyzer`:

```bash
python -m pytest tests/test_lifecycle.py tests/test_emerging.py tests/test_lifecycle_leader_evidence.py tests/test_emerging_reporting.py -q
```
