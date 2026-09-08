# Shared ThresholdOptimization

Analyzer별 점수 체계와 판정 철학은 유지하면서, threshold 최적화 절차만 공통화하는 모듈입니다.

공통 엔진이 담당하는 것:

- Grid Search
- Train 구간에서 상위 threshold 조합 선별
- Purged expanding Walk-Forward
- 미래 label overlap 방지용 trading-day purge
- 너무 짧은 trailing Validation fold 자동 제거
- 최소 표본/최소 날짜 Hard Constraint
- fold 내부 objective 표준화
- 미래 Validation 성능 평가
- validation 평균과 fold 편차를 함께 보는 robust score
- 인접 parameter 성능을 보는 plateau penalty
- 현재 설정에서 과도하게 멀어지는 parameter distance penalty
- 추천 신뢰도 `PROVISIONAL / ACCEPTABLE / ROBUST`
- current vs optimized 비교
- application-eligible threshold와 provisional threshold 분리 출력

Analyzer Adapter가 담당하는 것:

- 어떤 컬럼이 필요한지
- 어떤 threshold를 탐색할지
- parameter 조합이 후보를 선택하는 정확한 규칙
- 현재 threshold 값
- 추천값을 Analyzer config 형식으로 변환하는 규칙

## Objective profiles

공통 엔진은 Analyzer 목적에 따라 Objective profile을 바꿀 수 있습니다.

### `return_performance`

KJB / MA / Swing / Dynamic처럼 매매 신호 성격이 강한 Analyzer에 사용합니다.

기본적으로 중앙 수익률, 승률, 하방 분위수, MAE, excursion ratio, 표본 안정성을 조합합니다.

### `leadership_quality`

LeaderStockAnalyzer 전용입니다. LeaderStockAnalyzer의 목적은 미래 수익률 최대화가 아니라 **현재 시장의 실제 주도주를 판별하는 것**이므로 수익률을 Objective에서 제거했습니다.

기본 가중치:

```text
Leader Core retention 5D       30%
Market Rank TOP20 retention    20%
Persistence conversion 10D     15%
Trading Value TOP20 retention  15%
Sector leadership consistency  10%
False Leader avoidance         10%
```

`D+5`, `D+20` 수익률은 `current_vs_optimized.csv`에 진단값으로만 남고 threshold 선택 점수에는 들어가지 않습니다.

Leader Core label은 최적화 중인 CONFIRMED threshold 자체를 정답으로 사용하지 않습니다. 독립된 Lifecycle Core 기준인 `Leader Score >= 75` 및 `Market Leader Rank <= 20`을 사용해 자기참조를 피합니다.

## Adapter contract

```python
from ThresholdOptimization import BaseThresholdAdapter

class MyAnalyzerAdapter(BaseThresholdAdapter):
    analyzer_name = "MyAnalyzer"
    date_column = "scan_date"

    def parameter_space(self, optimizer_config): ...
    def current_parameters(self): ...
    def required_columns(self): ...
    def select_mask(self, df, params): ...
    def validate_parameters(self, params): ...
    def export_config(self, params): ...
```

따라서 Analyzer가 달라도 optimizer 본체를 복사하지 않습니다. 각 Analyzer에는 Adapter + optimizer config + 실행 BAT만 둡니다.

## 현재 연결된 Analyzer

| Analyzer | Objective | 기본 최적화 대상 |
|---|---|---|
| LeaderStockAnalyzer | `leadership_quality` | Leader / Timing / Chase / Breakout Quality / Strong Rank |
| KJBChartAnalyzer | `return_performance` | Selection / Timing / Leader / Relative Strength / Risk |
| MAChartAnalyzer | `return_performance` | Confirmed Score / Timing / MA20 이격, 이후 Strong Score / Timing |
| SwingChartProbabilityAnalyzer | `return_performance` | 기존 Confirmed 자격을 유지한 상태의 Score threshold |
| DynamicChartAnalyzer | `return_performance` | LONG Quality Score의 CONFIRMED threshold |

각 Analyzer의 원래 전략 조건은 Adapter에서 고정합니다.

- KJB: `reject_high_chase` 등 기존 confirmation_v1 철학 유지
- MA: Trend + Confirmed Trigger + Sideways/Long-MA Breakdown 차단 유지
- Swing: 하단 채널 + confirmation 구조를 바꾸지 않고 현재 CONFIRMED 자격 행만 재평가
- Dynamic: RSI -> MACD -> Ichimoku, Stage 1:2:7은 최적화 대상에서 제외

## Leader future leadership labels

Leader Range는 모든 날짜의 point-in-time 스캔이 끝난 뒤 사후적으로 다음 컬럼을 추가합니다.

- `leader_retention_5d`
- `market_top20_retention_5d`
- `turnover_top20_retention_5d`
- `persistence_conversion_10d`
- `sector_leader_retention_5d`
- `false_leader_5d`
- `leadership_quality_score`

미래 10거래일을 쓰는 Persistence label 때문에 Leader optimizer의 purge는 10거래일입니다.

기존 Range CSV에 이 컬럼이 없더라도 `LeaderStockAnalyzer/run_threshold_optimizer.py`가 Range의 날짜별 결과에서 자동으로 재구성할 수 있습니다.

## Walk-Forward 안전장치

기본 정책은 다음과 같습니다.

```yaml
min_valid_folds: 2
min_validation_fraction: 0.75
allow_provisional_fallback: true
acceptable_min_fold_coverage: 0.50
robust_min_valid_folds: 3
robust_min_fold_coverage: 0.75
```

예를 들어 Validation 길이가 40거래일이면 30거래일보다 짧은 마지막 partial fold는 버립니다.

`min_valid_folds: 2`는 **실제 적용 가능 threshold의 최소 조건**입니다. 이 기준을 못 채웠지만 한 개 이상의 유효 fold가 있으면 Optimizer는 분석을 중단하지 않고 `PROVISIONAL` 후보를 남깁니다. 다만 `eligible_for_application: false`로 기록되며 최종 `recommended_thresholds.yaml`에는 들어가지 않습니다.

## Recommendation confidence

- `PROVISIONAL`: 유효 OOS fold/coverage가 실제 적용 기준에 미달. 분석용으로만 사용.
- `ACCEPTABLE`: 최소 2개 유효 OOS fold와 요구 coverage를 충족. 적용 검토 가능.
- `ROBUST`: 최소 3개 유효 fold, 높은 fold coverage, 충분한 plateau neighbor, 낮은 plateau drop까지 충족.

공통 결과 폴더에는 다음 파일이 생성됩니다.

```text
recommendation_summary.yaml
recommended_thresholds.yaml
provisional_thresholds.yaml
```

`recommended_thresholds.yaml`에는 ACCEPTABLE / ROBUST만 들어갑니다. `provisional_thresholds.yaml`은 실험 참고용입니다.

## 실행

각 Analyzer에서 Range를 먼저 만든 후 해당 폴더의 BAT를 실행합니다.

```text
LeaderStockAnalyzer/run_optimize_thresholds.bat
KJBChartAnalyzer/run_optimize_thresholds.bat
MAChartAnalyzer/run_optimize_thresholds.bat
SwingChartProbabilityAnalyzer/run_optimize_thresholds.bat
DynamicChartAnalyzer/run_optimize_thresholds.bat
```

기본적으로 각 Analyzer의 최신 수정 Range 결과를 자동 탐색합니다. 추천값은 원본 config에 자동 반영하지 않습니다.

## 다른 Analyzer를 추가하는 순서

1. 기존 Range CSV의 컬럼 계약을 확인한다.
2. 해당 Analyzer의 CONFIRMED/WATCH 판정식을 Adapter의 `select_mask()`로 그대로 옮긴다.
3. Analyzer 목적에 맞는 `objective_profile`을 선택한다.
4. search space를 별도 YAML에 정의한다.
5. `run_threshold_optimizer.py`와 BAT를 해당 Analyzer 폴더에 둔다.
6. `recommendation_summary.yaml`의 confidence와 `eligible_for_application`을 확인한다.
7. `recommended_thresholds.yaml`에 들어간 값만 실제 적용 후보로 검토한다.

Optimizer가 Analyzer의 원래 철학을 바꾸면 안 됩니다. Threshold를 먼저 검증하고, 지표 기간·패턴 정의·가중치 같은 전략 자체의 파라미터는 별도 Weight/Strategy Optimization 단계에서 검토합니다.
