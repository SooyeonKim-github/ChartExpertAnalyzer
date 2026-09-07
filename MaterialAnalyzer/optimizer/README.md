# MaterialQualityOptimizer V1

`MaterialAnalyzer`의 목적은 **수익률이 높은 종목을 찾는 것**이 아니라 **시장에서 주목할 만한 재료를 놓치지 않고, 반복/행정성 노이즈를 줄이는 것**입니다.

따라서 기존 forward-return 기반 `MaterialThresholdOptimizer`는 폐기하고, derived pipeline의 품질을 직접 감사하는 `MaterialQualityOptimizer`로 개편합니다.

## 핵심 원칙

- D+5/D+20 수익률은 optimizer objective에 사용하지 않습니다.
- POSITIVE/NEGATIVE는 방향성이고 material importance와 분리합니다.
- 핵심 Event Type 누락률, UNKNOWN 비율, routine 과대승격, ticker direct-link coverage, unresolved rate, source coverage를 평가합니다.
- threshold 후보는 taxonomy quality 관점의 참고값일 뿐 자동 적용하지 않습니다.
- `apply_automatically=false`를 유지합니다.
- MaterialBacktester는 별도의 **사후 시장반응 진단기**로 남습니다.

## Material Score V2 배점

```text
Event Importance       30
Certainty              20
Directness             15
Scale / Quantification 15
Novelty                10
Source Reliability      5
Multi-source Confirm    5
                       ---
                       100
```

Material Score가 높다는 것은 "오를 가능성이 높다"가 아니라 "시장 참가자가 확인할 가치가 큰 재료"라는 뜻입니다.

## Quality Guardrails

기본적으로 다음을 확인합니다.

```text
UNKNOWN rate                  <= 20%
Core event below WATCH rate   <= 10%
High event below CONFIRMED    <= 25%
Direct ticker link coverage   >= 95%
Unresolved event rate         <= 5%
Routine promoted rate         <= 2%
Source coverage OK rate       >= 90%
```

Guardrail은 자동 production 설정이 아니라 품질 경고 기준입니다.

## 실행

먼저 최신 derived 결과가 필요합니다.

```bat
MaterialAnalyzer\run_material_range.bat --date-range 20260101~20260630 --derive-only
```

그 다음:

```bat
MaterialAnalyzer\run_material_optimizer.bat
```

입력은 아래 historical derived report입니다.

```text
MaterialAnalyzer\data\history\event_report.csv
MaterialAnalyzer\data\history\material_score_report.csv
MaterialAnalyzer\data\history\ticker_link_report.csv
MaterialAnalyzer\data\history\ticker_link_unresolved.csv
MaterialAnalyzer\data\history\historical_source_coverage.csv
```

`material_backtest_results.csv`는 읽지 않습니다.

## 출력

```text
MaterialAnalyzer\data\history\quality_optimizer\material_quality_metrics.csv
MaterialAnalyzer\data\history\quality_optimizer\material_quality_event_types.csv
MaterialAnalyzer\data\history\quality_optimizer\material_quality_threshold_candidates.csv
MaterialAnalyzer\data\history\quality_optimizer\material_quality_threshold_comparison.csv
MaterialAnalyzer\data\history\quality_optimizer\material_quality_recommendation.json
```

`material_quality_recommendation.json`에는 `uses_forward_returns=false`, `apply_automatically=false`가 기록됩니다.
