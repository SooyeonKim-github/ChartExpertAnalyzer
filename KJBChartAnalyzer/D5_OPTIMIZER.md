# KJB D+5 Threshold Optimizer

KJB를 D+5 단기 스윙 관점으로 검증하기 위한 전용 optimizer입니다.

## 실행

```bat
KJBChartAnalyzer\run_d5_optimizer.bat
```

최신 `KJBChartAnalyzer\results\range_*` 폴더를 자동으로 사용합니다.

실행 순서:

1. `d5_diagnostics.py`로 D+5 진단 결과 재생성
2. `d5_threshold_optimizer.py`로 250개 threshold 후보 탐색
3. D+5 label overlap 방지를 위해 각 OOS test 연도 직전 5개 거래일 purge
4. Expanding walk-forward 수행
   - 2020~2022 -> 2023
   - 2020~2023 -> 2024
   - 2020~2024 -> 2025
   - 2020~2025 -> 2026 (데이터가 존재하는 경우)
5. 각 test fold에서 기존 baseline과 optimized 성능 비교
6. fold별 train winner를 종합해 추천 threshold 생성

## 주요 탐색 항목

- `selection_min`
- `timing_min`
- `selection_weight` / timing weight
- `rs_hard`
- `leader_soft`, `leader_hard`
- `sector_soft`, `sector_hard`
- RS + Leader 복합 과열 penalty
- RS + Leader + Sector 복합 과열 penalty
- `overextension_max`
- `d5_score_min`
- `daily_top_n`: 1 / 3 / 5
- `regime`: all / uptrend+range / range / uptrend

RS 단독 고점은 무조건 감점하지 않고, Leader/Sector Leader 과열 및 복합 과열을 중심으로 검증합니다.

## Objective

D+5 지수 대비 alpha를 가장 중요하게 봅니다.

- 평균 D+5 excess return: 35%
- 중앙 D+5 excess return: 15%
- 평균 D+5 return: 20%
- 중앙 D+5 return: 10%
- D+5 하방 20% 분위수: 5%
- D+5 승률: 7.5%
- excess 승률: 7.5%
- 연도별 excess 변동성: penalty 10%

## 결과 파일

최신 `results\range_*` 폴더에 생성됩니다.

- `kjb_d5_optimizer_trials.csv`: fold별 train 후보 전체
- `kjb_d5_walkforward.csv`: fold별 OOS 성능 및 baseline 비교
- `kjb_d5_optimizer_summary.csv`: 추천 threshold와 OOS 평균
- `kjb_d5_optimizer_best.json`: 추천값, 신뢰도, 적용 가능 여부
- `chart_range_events_d5_optimized.csv`: 추천 threshold를 전체 데이터에 적용한 참고 결과

## 신뢰도

`recommendation_confidence`:

- `ROBUST`: 3개 이상 유효 OOS fold, 평균 excess > 0, 양(+) excess fold 비율 >= 75%, baseline 대비 평균 개선이 음수가 아님
- `ACCEPTABLE`: 2개 이상 유효 OOS fold, 평균 excess > 0, 양(+) excess fold 비율 >= 50%
- `PROVISIONAL`: 위 조건 미달. 실전 설정에 바로 반영하지 않고 추가 검증용으로 사용

실제 적용 후보로 볼 때는 `eligible_for_application=true`인지 먼저 확인합니다.

## 주의

현재 Range Universe가 KOSPI-only로 생성된 경우 optimizer 결과 역시 KOSPI 기준입니다. KOSDAQ까지 실전에 포함하려면 KOSDAQ Universe가 정상 포함된 Range를 먼저 만든 뒤 optimizer를 다시 실행해야 합니다.
