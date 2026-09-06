# Exhaustion Risk V1.1

`ExhaustionRiskEngine` estimates whether an established leader is **rolling over from a recent peak**, before a confirmed structural breakdown.

V1.1 remains **observational only**. It does not change:

- Leader Score
- Timing Score
- STRONG_CONFIRMED / CONFIRMED / WATCH / REJECT
- Lifecycle state

The first V1 backtest showed that raw overextension was not predictive enough: strong healthy leaders are often far above MA20 and extended by ATR. V1.1 therefore changes the question from:

```text
How far has the leader already risen?
```

to:

```text
After becoming strong, how much has momentum / leadership / money flow / structure deteriorated from its recent peak?
```

## Score

```text
Overextension Context             5
Momentum Rollover                30
Distribution / Breakout Failure  25
Money-flow / Rank Decay          20
Structure Deterioration          20
-----------------------------------
Total                           100
```

Default labels are unchanged for clean attribution against V1:

```text
0 ~ 34    LOW
35 ~ 54   WATCH
55 ~ 74   HIGH
75 ~ 100  CRITICAL
```

## 1. Overextension Context — 5

Overextension is now only supporting context.

Uses:

- MA20 distance
- 5-day return
- ATR-normalized extension
- Chase Risk

A stock does **not** become HIGH merely because it is strongly extended.

```text
MA20 +20%
ATR 3x
strong 5-day return

=> context points only
```

The score becomes meaningful when extension is followed by rollover evidence.

## 2. Momentum Rollover — 30

This is the primary V1.1 component.

Uses:

- current 3-day momentum
- highest 3-day momentum observed during the recent 10-day price window
- drop from that momentum peak
- current 3-day return vs the previous 3-day return
- Leader Score peak over the previous 5 observed scan dates
- Leader Score decay from that peak
- RS peak over the previous 5 observed scan dates
- RS decay from that peak
- negative day after a strong momentum peak

Example:

```text
3-day momentum peak   +16%
current 3-day momentum +2%

momentum drop = 14%p
```

and:

```text
Leader Score peak  92
current score      63

Leader Score decay = 29
```

Range scans reuse one `ExhaustionRiskEngine` instance across scan dates, so Leader Score / RS / Persistence peak values are point-in-time historical observations only. No future observation is used.

## 3. Distribution / Breakout Failure — 25

Reuses existing Breakout Quality evidence with increased importance:

- `false_breakout_flag`
- `breakout_exhaustion_risk`
- long upper wick
- weak close location
- high-volume down day

This component is intended to identify actual selling pressure rather than simple price extension.

## 4. Money-flow / Rank Decay — 20

Uses shared `LeadershipHistoryContext` plus observed Persistence history:

- 3-day trading-value rank reversal
- 5-day trading-value rank reversal
- current trading value vs recent 5-day peak
- Persistence Score peak over previous observations
- Persistence Score decay from that peak
- currently weak Persistence Score

Example:

```text
Trading-value rank
3 -> 5 -> 12 -> 27

Trading value
peak 400B -> current 130B
```

This is stronger exhaustion evidence than simply being highly ranked today.

## 5. Structure Deterioration — 20

V1.1 focuses on **deterioration speed**, not only absolute MA breaks.

Uses:

- MA10 distance decay from recent peak
- MA20 distance decay from recent peak
- drawdown from the 20-day high
- MA10 break
- MA20 break
- MA20 5-day slope

Example:

```text
MA20 distance
+18% -> +14% -> +8% -> +2%
```

The stock is still above MA20, but leadership structure is deteriorating quickly.

## Output columns

Existing V1 diagnostics remain, with additional V1.1 fields:

```text
exhaustion_risk_available
exhaustion_risk_score
exhaustion_risk_label

exhaustion_overextension_score
exhaustion_deceleration_score
exhaustion_distribution_score
exhaustion_money_flow_decay_score
exhaustion_structure_score

exhaustion_momentum_3d
exhaustion_momentum_peak_10d
exhaustion_momentum_drop_from_peak

exhaustion_leader_score_peak_5obs
exhaustion_leader_score_decay

exhaustion_rs_current
exhaustion_rs_peak_5obs
exhaustion_rs_decay_from_peak

exhaustion_persistence_peak_5obs
exhaustion_persistence_decay_from_peak

rank_reversal_3d
rank_reversal_5d
trading_value_decay_ratio

exhaustion_distance_ma10_pct
exhaustion_distance_ma20_pct
exhaustion_distance_ma10_decay_5d
exhaustion_distance_ma20_decay_5d
exhaustion_ma10_slope_5d_pct
exhaustion_ma20_slope_5d_pct
exhaustion_drawdown_20d_pct
```

## Range validation

`main_range.py` writes:

```text
exhaustion_events.csv
exhaustion_summary.csv
exhaustion_score_report.csv
```

### exhaustion_events.csv

A new `HIGH` or `CRITICAL` episode while the stock is in:

```text
LEADER
PERSISTENT_LEADER
```

It tracks:

- 3/5/10 observed-session transition to EXHAUSTING
- 3/5/10 observed-session transition to BROKEN
- D+5 / D+20 / D+60
- MFE / MAE when available

### exhaustion_summary.csv

Episode summary for:

```text
ALL
HIGH
CRITICAL
```

### exhaustion_score_report.csv

This report is important for V1.1 validation. It compares **all established leader observations**, not only HIGH/CRITICAL events:

```text
LOW
WATCH
HIGH
CRITICAL
```

and reports count, average Exhaustion Score, forward returns, win rate, MFE and MAE.

## Validation target

Do not connect V1.1 to Lifecycle until the range backtest shows a stable ordering such as:

```text
LOW/WATCH
  -> better D+20
  -> smaller adverse excursion

HIGH/CRITICAL
  -> weaker D+20
  -> larger adverse excursion
  -> higher future EXHAUSTING/BROKEN rate
```

If this ordering is not present, tune the component logic again rather than simply lowering the HIGH threshold.
