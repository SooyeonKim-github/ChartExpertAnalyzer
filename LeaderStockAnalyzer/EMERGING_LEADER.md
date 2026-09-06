# Emerging Leader / Rank Velocity

`EmergingLeaderEngine` detects stocks whose market leadership is accelerating, rather than simply selecting stocks that already have a high trading-value rank.

## Score

```text
Rank Velocity               50
Trading-value Acceleration  25
Relative-strength Accel.    15
Freshness                   10
------------------------------
Total                      100
```

Default labels:

```text
85~100  STRONG_EMERGING
70~84   EMERGING
55~69   WATCH
0~54    NOT_EMERGING
```

`true_emerging_flag` additionally requires the configured Chase Risk limit and rejects breakout-exhaustion / false-breakout conditions.

`strong_emerging_flag` requires:

- Emerging Leader Score >= 85
- current candidate-pool trading-value rank <= 15
- 5-day rank improvement >= 30 places
- no chase/exhaustion gate failure

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

- `emerging_leader_score`
- `emerging_label`
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

When Emerging Leader data is available, normal `DISCOVERY -> EMERGING` promotion requires `true_emerging_flag` and the Lifecycle hysteresis confirmation.

`STRONG_EMERGING` may fast-track `DISCOVERY -> EMERGING` in one observation.

Once a stock is already `EMERGING`, Rank Velocity is allowed to cool. Promotion to `LEADER` is then controlled by established Leader Score / rank / persistence evidence.

## Range validation reports

`main_range.py` additionally writes:

```text
emerging_events.csv
emerging_summary.csv
```

`emerging_events.csv` keeps one row per Emerging lifecycle episode start and includes forward performance plus future lifecycle outcomes.

`emerging_summary.csv` reports:

- 3/5/10 observed-session LEADER transition rate
- 3/5/10 observed-session PERSISTENT_LEADER rate
- DISCOVERY return rate
- BROKEN rate
- D+5 / D+20 / D+60 average, median and win rate

The first KPI to compare against Lifecycle V2 is the false-emerging rate: an Emerging episode that returns to DISCOVERY shortly after activation.
