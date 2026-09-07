# MaterialThresholdOptimizer V1

MaterialBacktester 결과를 사용해 **후보 점수 보정값과 STRONG/CONFIRMED/WATCH threshold를 탐색**합니다.

중요 원칙:

- MaterialScorer 설정을 자동으로 덮어쓰지 않습니다.
- 결과는 `baseline vs optimized_candidate` 검증용입니다.
- 같은 종목/같은 날 여러 공시는 inverse ticker-day weight로 과대반영을 줄입니다.
- Event Type, Novelty, Relation, Polarity, Quantification 효과는 train 구간에서만 학습합니다.
- 표본이 작은 그룹은 shrinkage + min-sample guard를 적용합니다.
- 기본 분할은 날짜 기준 앞 80% train / 뒤 20% validation입니다.
- 장기 검증에서는 `--train-end 20251231 --validation-start 20260101` 같은 명시적 분할을 권장합니다.

## 실행

```bat
MaterialAnalyzer\run_material_optimizer.bat
```

명시적 검증 구간:

```bat
MaterialAnalyzer\run_material_optimizer.bat --train-end 20251231 --validation-start 20260101 --min-sample 100
```

입력:

```text
MaterialAnalyzer\data\history\backtest\material_backtest_results.csv
```

출력:

```text
MaterialAnalyzer\data\history\optimizer\material_optimizer_scored.csv
MaterialAnalyzer\data\history\optimizer\material_optimizer_weights.csv
MaterialAnalyzer\data\history\optimizer\material_optimizer_candidates.csv
MaterialAnalyzer\data\history\optimizer\material_optimizer_validation.csv
MaterialAnalyzer\data\history\optimizer\material_optimizer_recommendation.json
```

`material_optimizer_recommendation.json`의 `apply_automatically`는 항상 `false`입니다. 후보가 validation에서 좋아도 충분한 장기 out-of-sample 검증 전에는 MaterialScorer에 반영하지 않습니다.
