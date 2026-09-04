# Shared ThresholdOptimization

Analyzer별 점수 체계와 판정 철학은 유지하면서, threshold 최적화 절차만 공통화하는 모듈입니다.

공통 엔진이 담당하는 것:

- Grid Search
- Purged expanding Walk-Forward
- D+n label leakage 방지용 trading-day purge
- 최소 표본/최소 날짜 Hard Constraint
- fold 내부 objective 표준화
- validation 평균과 fold 편차를 함께 보는 robust score
- 인접 parameter 성능을 보는 plateau penalty
- 현재 설정에서 과도하게 멀어지는 parameter distance penalty
- current vs optimized 비교
- recommended_thresholds.yaml 출력

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

## 권장 전제

Range 결과에는 최소한 다음이 있어야 합니다.

- 날짜 컬럼 (`scan_date` 권장)
- 최적화할 score/risk 컬럼
- `D+20` 같은 완전한 forward return

가능하면 다음도 공통으로 추가하는 것이 좋습니다.

- `MAE_D20`
- `MFE_D20`
- `excursion_ratio_D20`

이 세 값이 있으면 단순 수익률 최대화가 아니라 하방 위험과 경로 품질까지 같이 최적화할 수 있습니다.

## 다른 Analyzer에 붙이는 순서

1. 기존 Range CSV의 컬럼 계약을 확인한다.
2. 해당 Analyzer의 CONFIRMED/WATCH 판정식을 Adapter의 `select_mask()`로 그대로 옮긴다.
3. search space를 별도 YAML에 정의한다.
4. `run_threshold_optimizer.py`와 BAT를 해당 Analyzer 폴더에 둔다.
5. 추천값은 기존 config를 자동 덮어쓰지 않고 `recommended_thresholds.yaml`로만 출력한다.
6. 충분한 기간에서 Walk-Forward 결과가 안정적인지 확인한 뒤 수동 반영한다.

Optimizer가 Analyzer의 원래 철학을 바꾸면 안 됩니다. 예를 들어 KJB의 Selection/Timing, MA의 패턴/Timing, Swing의 단계·확률 구조는 각각 Adapter에 보존해야 합니다.
