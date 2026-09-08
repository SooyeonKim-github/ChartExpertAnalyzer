# KJB D+5 FINAL V1

KJBChartAnalyzer의 국내 실전 스크린 정책은 D+5 FINAL V1로 고정한다.

## 왜 이 버전을 production으로 쓰는가

D+5 diagnostics에서 OverextensionPenalty가 과열군을 유의미하게 분리했다.
Threshold Optimizer V2는 purged walk-forward에서 baseline을 이기지 못해 PROVISIONAL로 판정되었다.
따라서 optimizer 추천값을 production에 적용하지 않고, 검증된 baseline을 고정한다.

## Frozen parameters

```yaml
selection_weight: 0.45
timing_weight: 0.55
selection_min: 70
timing_min: 72
d5_score_min: 70
overextension_max_exclusive: 8
rs_hard: 92
leader_soft: 80
leader_hard: 88
sector_soft: 78
sector_hard: 86
combo_rs_leader_penalty: 3
combo_triple_penalty: 4
daily_top_n: 3
market_regime: all
```

Market Regime은 production 종목 선별 조건이나 점수 가감에 사용하지 않고 정보로만 남긴다.

## Live decision flow

```text
Raw KJB analysis
  -> baseline CONFIRMED prerequisite
  -> live Sector Leader context (same scoring function as range)
  -> D+5 Selection/Timing score
  -> Leader/Sector overextension penalty
  -> penalty < 8
  -> d5_adjusted_score >= 70
  -> D5_CONFIRMED
  -> daily d5_adjusted_score TOP3
  -> operational Status=CONFIRMED
```

Baseline WATCH는 D+5 정책이 CONFIRMED로 승격하지 않는다.

## Output columns

`KJBChartAnalyzer/output/top100_screen.csv`에서:

- `Baseline_Status`: 기존 confirmation_v1 결과
- `D5_Status`: 전체 D+5 자격 (`D5_CONFIRMED`, `D5_WATCH`, `D5_REJECTED`)
- `D5_Selected`: Daily Top3 여부
- `Status`: 실제 downstream에서 사용하는 operational 상태
- `score`: production ranking용 `d5_adjusted_score`
- `raw_selection_score`: 기존 Selection 점수
- `overextension_penalty`: FINAL V1 과열 감점
- `sector_leader_score`: Range와 같은 Sector Leader 함수 결과
- `d5_policy_version`: `KJB_D5_FINAL_V1`

`Status=CONFIRMED`만 루트 `scripts/aggregate_confirmed_candidates.py`에 의해 누적되므로 KJB history에는 Daily Top3 production 후보만 들어간다.

## Main execution

Repository root에서:

```bat
run_screen_kr.bat
```

KJB 단계는 `app.py screen-top100`을 실행하고 D+5 FINAL V1을 자동 적용한다.

## Optimizer policy

`d5_threshold_optimizer_v2.py`는 연구/재검증용으로 보존한다.
현재 PROVISIONAL optimizer 추천값은 production config에 자동 반영하지 않는다.
KJB 정책을 다시 변경하려면 새로운 OOS/Walk-forward 결과가 baseline을 안정적으로 이기는 근거가 먼저 필요하다.
