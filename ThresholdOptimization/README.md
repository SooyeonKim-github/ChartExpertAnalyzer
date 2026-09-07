# Shared ThresholdOptimization

Analyzer별 점수 체계와 판정 철학은 유지하면서, threshold 최적화 절차만 공통화하는 모듈입니다.

공통 엔진이 담당하는 것:

- Grid Search
- Train 구간에서 상위 threshold 조합 선별
- Purged expanding Walk-Forward
- D+n label leakage 방지용 trading-day purge
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

| Analyzer | Adapter | 기본 최적화 대상 |
|---|---|---|
| LeaderStockAnalyzer | `leader_stock_analyzer/optimization/adapter.py` | Leader / Timing / Chase / Breakout Quality / Strong Rank |
| KJBChartAnalyzer | `optimization/adapter.py` | Selection / Timing / Leader / Relative Strength / Risk |
| MAChartAnalyzer | `optimization/adapter.py` | Confirmed Score / Timing / MA20 이격, 이후 Strong Score / Timing |
| SwingChartProbabilityAnalyzer | `optimization/adapter.py` | 기존 Confirmed 자격을 유지한 상태의 Score threshold |
| DynamicChartAnalyzer | `optimization/adapter.py` | LONG Quality Score의 CONFIRMED threshold |

각 Analyzer의 원래 전략 조건은 Adapter에서 고정합니다.

- KJB: `reject_high_chase` 등 기존 confirmation_v1 철학 유지
- MA: Trend + Confirmed Trigger + Sideways/Long-MA Breakdown 차단 유지
- Swing: 하단 채널 + confirmation 구조를 바꾸지 않고 현재 CONFIRMED 자격 행만 재평가
- Dynamic: RSI -> MACD -> Ichimoku, Stage 1:2:7은 최적화 대상에서 제외

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

예를 들어 Validation 길이가 40거래일이면 30거래일보다 짧은 마지막 partial fold는 버립니다. 따라서 2거래일짜리 꼬리 구간이 독립적인 Validation fold처럼 취급되지 않습니다.

`min_valid_folds: 2`는 **실제 적용 가능 threshold의 최소 조건**입니다. 이 기준을 못 채웠지만 한 개 이상의 유효 fold가 있으면 Optimizer는 분석을 중단하지 않고 `PROVISIONAL` 후보를 남깁니다. 다만 `eligible_for_application: false`로 기록되며 최종 `recommended_thresholds.yaml`에는 들어가지 않습니다.

## Recommendation confidence

각 trial과 최종 후보는 다음 등급을 가집니다.

- `PROVISIONAL`: 유효 OOS fold/coverage가 실제 적용 기준에 미달. 분석용으로만 사용.
- `ACCEPTABLE`: 최소 2개 유효 OOS fold와 요구 coverage를 충족. 적용 검토 가능.
- `ROBUST`: 최소 3개 유효 fold, 높은 fold coverage, 충분한 plateau neighbor, 낮은 plateau drop까지 충족.

공통 결과 폴더에는 추가로 다음 파일이 생성됩니다.

```text
recommendation_summary.yaml
```

주요 항목:

```yaml
recommendation_quality: PROVISIONAL
eligible_for_application: false
recommended_params: ...
diagnostics:
  total_walk_forward_folds: 2
  required_valid_folds: 2
  best_valid_folds: 1
  best_fold_coverage: 0.5
  used_provisional_fallback: true
```

각 Analyzer 실행기는 최종 파일도 분리합니다.

```text
recommended_thresholds.yaml   # ACCEPTABLE / ROBUST만 포함
provisional_thresholds.yaml   # PROVISIONAL 후보만 포함
```

따라서 `provisional_thresholds.yaml`은 실험 참고용이며 production config에 바로 복사하지 않습니다.

## 실행

각 Analyzer에서 Range를 먼저 만든 후 해당 폴더의 아래 BAT를 실행합니다.

```text
LeaderStockAnalyzer/run_optimize_thresholds.bat
KJBChartAnalyzer/run_optimize_thresholds.bat
MAChartAnalyzer/run_optimize_thresholds.bat
SwingChartProbabilityAnalyzer/run_optimize_thresholds.bat
DynamicChartAnalyzer/run_optimize_thresholds.bat
```

기본적으로 각 Analyzer의 최신 수정 Range 결과를 자동 탐색합니다. 추천값은 원본 config에 자동 반영하지 않습니다.

## 권장 전제

Range 결과에는 최소한 다음이 있어야 합니다.

- 날짜 컬럼
- 최적화할 score/risk 컬럼
- `D+20` 같은 완전한 forward return

가능하면 다음도 공통으로 추가하는 것이 좋습니다.

- `MFE_D20`
- `MAE_D20`
- `excursion_ratio_D20`

현재 Leader와 Swing은 D+20 경로 품질을 목적함수에 직접 반영할 수 있습니다. KJB/MA/Dynamic은 기존 Range 포맷의 MFE/MAE horizon이 서로 달라 우선 각 target return/승률/P25/표본 안정성 중심으로 연결했습니다. 다음 공통화 단계에서 다섯 Analyzer 모두 동일한 성과 컬럼 계약으로 맞추는 것을 권장합니다.

## 다른 Analyzer를 추가하는 순서

1. 기존 Range CSV의 컬럼 계약을 확인한다.
2. 해당 Analyzer의 CONFIRMED/WATCH 판정식을 Adapter의 `select_mask()`로 그대로 옮긴다.
3. search space를 별도 YAML에 정의한다.
4. `run_threshold_optimizer.py`와 BAT를 해당 Analyzer 폴더에 둔다.
5. `recommendation_summary.yaml`의 confidence와 `eligible_for_application`을 확인한다.
6. `recommended_thresholds.yaml`에 들어간 값만 실제 적용 후보로 검토한다.
7. 충분한 기간에서 Walk-Forward 결과가 안정적인지 확인한 뒤 수동 반영한다.

Optimizer가 Analyzer의 원래 철학을 바꾸면 안 됩니다. 최적화는 먼저 판정 threshold를 대상으로 하고, 지표 기간·패턴 정의·강의 원형 같은 전략 자체의 파라미터는 별도 Weight/Strategy Optimization 단계에서 검토합니다.
