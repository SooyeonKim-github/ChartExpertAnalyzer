# Emerging Leader / Rank Velocity V1.1

`EmergingLeaderEngine` detects stocks whose market leadership is accelerating, while separating genuine early leadership from late momentum spikes.

## Base score

```text
Rank Velocity               50
Trading-value Acceleration  25
Relative-strength Accel.    15
Freshness                   10
------------------------------
Raw Score                  100
```

V1.1 then subtracts an Overheat Penalty:

```text
Emerging Leader Score = Raw Score - Overheat Penalty
```

Default labels:

```text
85~100  STRONG_EMERGING
70~84   EMERGING
55~69   WATCH
0~54    NOT_EMERGING
        MOMENTUM_SPIKE  when overheat conditions are triggered
```

## V1.1 tuning

The first Rank Velocity backtest showed that extreme acceleration often represented a late short-term spike rather than a high-quality early leader. V1.1 therefore applies:

- `max_chase_risk = 40`
- daily-return overheat penalty starting at +15%
- stronger penalty at +20%
- RS-acceleration penalty starting at +16
- stronger penalty above +25
- price + turnover spike penalty when 5-day trading-value ratio is extreme
- `MOMENTUM_SPIKE` classification for excessive acceleration / chase risk

`MOMENTUM_SPIKE` rows are never `true_emerging_flag=true`.

## Rank history

During range analysis, rank history is calculated from the preloaded candidate pool, not only the final daily TOP100.

With the default configuration:

```text
TOP N = 100
candidate_multiplier = 3
candidate rank history = TOP300 candidate pool
```

This lets the analyzer distinguish:

```text
70 -> 45 -> 22 -> 11 -> 6   newly emerging
 5 ->  8 ->  6 ->  7 -> 6   already established
```

## Output columns

Important V1.1 fields:

- `emerging_raw_score`
- `emerging_leader_score`
- `emerging_label`
- `emerging_overheat_penalty`
- `emerging_overheat_flags`
- `momentum_spike_flag`
- `emerging_rank_today`
- `emerging_rank_1d_ago`
- `emerging_rank_3d_ago`
- `emerging_rank_5d_ago`
- `rank_velocity_1d`
- `rank_velocity_3d`
- `rank_velocity_5d`
- `rank_percentile_velocity_5d`
- `rank_acceleration`
- `trading_value_ratio_5d`
- `trading_value_ratio_20d`
- `trading_value_acceleration`
- `emerging_rs_3d`
- `emerging_rs_5d`
- `emerging_rs_acceleration`
- component scores
- `true_emerging_flag`
- `strong_emerging_flag`

## Lifecycle integration

When Emerging Leader data is available, `DISCOVERY -> EMERGING` requires `true_emerging_flag` plus Lifecycle hysteresis confirmation.

Default V2.2 behavior:

```text
promotion_confirm_days = 2
allow_strong_emerging_fast_track = false
```

So even `STRONG_EMERGING` normally needs repeated confirmation. Fast-track can still be explicitly re-enabled for experiments, but it is not the default.

Once a stock is already `EMERGING`, Rank Velocity is allowed to cool. Promotion to `LEADER` is controlled by established Leader Score / rank / persistence evidence.

## Range validation reports

`main_range.py` writes:

```text
emerging_events.csv
emerging_summary.csv
```

`emerging_events.csv` contains only the first row of each qualifying EMERGING episode and adds `event_type`:

```text
INITIAL_INFERENCE
RANK_VELOCITY_CONFIRMED
FAST_TRACK
OTHER
```

`emerging_summary.csv` contains an `ALL` row plus one row per event cohort and reports:

- 3/5/10-session LEADER transition rate
- PERSISTENT_LEADER transition rate
- DISCOVERY return rate
- false-emerging rate
- BROKEN rate
- D+5 / D+20 / D+60 average, median and win rate

The primary KPI for V1.1 is `RANK_VELOCITY_CONFIRMED`: improve its LEADER conversion rate while reducing its false-emerging rate.
