# Exhaustion Risk V1

`ExhaustionRiskEngine` scores whether an active leader is losing quality before a confirmed structural breakdown.

V1 is **observational only**. It does not change:

- Leader Score
- Timing Score
- STRONG_CONFIRMED / CONFIRMED / WATCH / REJECT
- Lifecycle state

The purpose of V1 is to backtest whether high exhaustion scores predict weaker forward returns, larger MAE, and later `EXHAUSTING` / `BROKEN` transitions.

## Score

```text
Overextension / Heat          25
Momentum Deceleration         25
Distribution / Breakout Fail  20
Money-flow / Rank Decay       15
Price Structure Damage        15
--------------------------------
Total                        100
```

Default labels:

```text
0 ~ 34    LOW
35 ~ 54   WATCH
55 ~ 74   HIGH
75 ~ 100  CRITICAL
```

## 1. Overextension / Heat — 25

Uses:

- distance from MA20
- 5-day return
- ATR-normalized extension
- existing Chase Risk

Examples of risk evidence:

```text
MA20 distance >= +15~20%
5-day return >= +15~25%
ATR extension >= 2~3 ATR
Chase Risk >= 50~70
```

This component tries to separate a healthy leader from a parabolic leader that may already be late in the move.

## 2. Momentum Deceleration — 25

Uses:

- latest 3-day return vs previous 3-day return
- RS deceleration
- Rank Velocity reversal
- negative day after a fast 5-day run

Conceptually:

```text
previous 3d +15%
latest   3d  +4%

=> price momentum deceleration
```

A leader can still be near its high while its rate of advance is already weakening.

## 3. Distribution / Breakout Failure — 20

Reuses existing Breakout Quality evidence:

- `false_breakout_flag`
- `breakout_exhaustion_risk`
- long upper wick
- weak close location
- high-volume down day

This is intended to identify selling pressure appearing near the top of a leadership move.

## 4. Money-flow / Rank Decay — 15

Uses shared `LeadershipHistoryContext`:

- 3-day trading-value rank reversal
- 5-day trading-value rank reversal
- current trading value vs recent 5-day peak
- Persistence Score decay

Example:

```text
Trading-value rank
3 -> 5 -> 12 -> 27

price still near high
=> money-flow decay before visible price damage
```

## 5. Price Structure Damage — 15

Uses:

- drawdown from 20-day high
- MA10 break
- MA20 break
- 5-day change in MA20

The distinction is intentional:

```text
MA10 break / moderate drawdown
=> possible exhaustion

MA20 break + deep drawdown / large selloff
=> existing Lifecycle BROKEN evidence
```

## Output columns

Important columns include:

```text
exhaustion_risk_available
exhaustion_risk_score
exhaustion_risk_label

exhaustion_overextension_score
exhaustion_deceleration_score
exhaustion_distribution_score
exhaustion_money_flow_decay_score
exhaustion_structure_score

exhaustion_flags
exhaustion_return_5d
exhaustion_return_10d
price_momentum_deceleration
rs_deceleration
rank_reversal_3d
rank_reversal_5d
trading_value_decay_ratio
exhaustion_distance_ma10_pct
exhaustion_distance_ma20_pct
atr_extension
exhaustion_ma20_slope_5d_pct
exhaustion_drawdown_20d_pct
exhaustion_below_ma10
exhaustion_below_ma20
```

## Range validation

`main_range.py` writes:

```text
exhaustion_events.csv
exhaustion_summary.csv
```

An event is a new `HIGH` or `CRITICAL` risk episode while the stock is in:

```text
LEADER
PERSISTENT_LEADER
```

The report measures:

- 3/5/10 observed-session transition to `EXHAUSTING`
- 3/5/10 observed-session transition to `BROKEN`
- D+5 / D+20 / D+60 return
- D+20 / D+60 MFE
- D+20 / D+60 MAE

## Validation target

Before connecting the score to Lifecycle, check whether:

```text
LOW/WATCH leaders
vs
HIGH/CRITICAL leaders
```

show a stable difference in:

- forward return
- MAE
- MFE
- subsequent EXHAUSTING rate
- subsequent BROKEN rate

Only after that validation should the existing Lifecycle `exhausting_min_flags` heuristic be replaced or augmented by `exhaustion_risk_score`.
