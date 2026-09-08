# TrendFollowingAnalyzer

추세추종 강의의 매매 의사결정을 독립 Analyzer로 구현합니다.

## 개발 로드맵

1. 프로젝트 뼈대 ✅
2. MA50 / MA150 ✅
3. Stage Detector ✅
4. Market Regime
   - 4A. 지수 vs MA150 + MA150 기울기 ✅
   - 4B. 52주 신고가 Breadth ✅
   - 4C. 전약후강 / 전강후약 Daily OHLC Proxy ✅
   - 4D. 호재/악재 민감도 ⏸ 보류
5. Relative Strength ✅
6. Prior Advance ✅
7. Generic Base Detector ✅
   - 7.1 Base 실패 상태 세분화 ✅
8. Volume Contraction ✅
9. Breakout Detector ✅
10. V1 Range Backtest ✅
11. VCP
12. Cup With Handle
13. Initial Stop
14. High Volume Reversal
15. MA50 / MA150 Trend Exit
16. Score
17. Threshold Optimizer
18. Ablation Backtest

## 원칙

`LECTURE_CORE`와 구현상 추가한 `EXPERIMENTAL`을 구분합니다. 검증 전 지표는 `BACKTEST_ONLY`로 저장하며, 현재 실시간 `ACTIVE_FILTER`는 종목 `STAGE_2`와 해당 시장 `BULL`뿐입니다. Base, Prior Advance, Volume Contraction, Breakout의 수치 임계값은 아직 실시간 후보를 제거하지 않습니다.

## Phase 7.1 - Base 진단 세분화

Base가 탐지되지 않았을 때 최대 60일 창 하나를 모두 `TOO_DEEP`으로 처리하지 않고 가장 가까운 후보를 기준으로 실패 원인을 분리합니다.

```text
BASE_DETECTED
TOO_DEEP
TOO_FAR_FROM_HIGH
TOO_LOOSE
NO_RESISTANCE_ANCHOR
NO_BASE
INSUFFICIENT
```

함께 저장하는 진단값:

```text
base_status_reason
base_experimental_depth_pass
base_experimental_end_near_high_pass
base_experimental_resistance_pass
base_experimental_atr_contraction_pass
base_experimental_range_contraction_pass
```

## Phase 8 - Volume Contraction

실제 `base_start_date ~ scan_date` 안에서 거래량이 줄어드는지 측정합니다. 돌파일 거래량이 수축 계산을 오염시키지 않도록 기본적으로 마지막 세션은 제외합니다.

주요 지표:

```text
volume_early_avg / volume_late_avg
volume_contraction_ratio
volume_early_median / volume_late_median
volume_median_contraction_ratio
volume_5d_vs_20d / volume_5d_vs_50d
up_day_volume_avg / down_day_volume_avg
down_vs_up_volume_ratio
dry_up_day_ratio
volume_experimental_quality_score
```

기본 실험 임계값은 `late/early <= 0.80`, 하락일/상승일 거래량 비율 `<= 1.0` 등이며 전부 `EXPERIMENTAL + BACKTEST_ONLY`입니다.

## Phase 9 - Breakout Detector

오늘 종가를 판단할 때 **전일까지 탐지된 Base**만 사용합니다. 따라서 오늘 데이터로 Base 저항선을 다시 그려 돌파를 판정하지 않습니다.

상태:

```text
BREAKOUT_CONFIRMED
BREAKOUT_WEAK_VOLUME
INTRADAY_REJECTED
NEAR_BREAKOUT
NOT_BREAKOUT
NO_BASE
INSUFFICIENT
```

주요 지표:

```text
breakout_level
breakout_close_breakout_pct
breakout_intraday_high_breakout_pct
breakout_gap_pct
breakout_close_location_value
breakout_volume_ratio
breakout_experimental_false_breakout
breakout_experimental_signal_pass
```

기본 거래량 확인값 `1.50x` 역시 실험값입니다.

## 단일 날짜 실행

```bat
run_screen.bat
```

결과:

```text
results/<YYYYMMDD>/
├─ stage_market_screen.csv
├─ stage2_candidates.csv
├─ lecture_core_candidates.csv
├─ market_breadth_summary.csv
├─ market_intraday_summary.csv
├─ relative_strength_summary.csv
├─ prior_advance_summary.csv
├─ base_summary.csv
├─ volume_contraction_summary.csv
├─ breakout_summary.csv
└─ rule_catalog.csv
```

## Phase 10 - V1 Range Backtest

`run_range_backtest.bat`으로 날짜 범위를 입력해 실행합니다.

```bat
run_range_backtest.bat
```

또는:

```bat
python main_range.py --date-range 20260101~20260831 --top-n 100
```

V1 백테스트 원칙:

- 매일 KOSPI+KOSDAQ **point-in-time snapshot**으로 거래대금 Top-N을 다시 구성
- snapshot이 없는 날짜를 현재 Excel 구성종목으로 몰래 대체하지 않음
- 신호 계산은 해당 날짜까지의 데이터만 사용
- Breakout은 전일까지의 Base를 사용
- 진입가는 신호일 종가
- 사후수익률은 D+5 / D+20 / D+60 종가 기준
- 마지막 구간처럼 미래 데이터가 부족하면 `complete_count`에서 제외
- V1은 포지션 중복 제거 없는 signal-level event study이며 실제 포트폴리오 백테스트와 구분

전략 bucket:

```text
CORE
CORE_BASE
CORE_BASE_PRIOR
CORE_BASE_VOLUME
CORE_BASE_PRIOR_VOLUME
CORE_BREAKOUT
CORE_FULL_STACK
```

결과:

```text
results_range/<YYYYMMDD_YYYYMMDD>/
├─ range_all_results.csv
├─ range_core_results.csv
├─ range_candidates.csv
├─ range_strategy_summary.csv
├─ range_errors.csv
├─ range_meta.csv
└─ range_meta.json
```

`range_strategy_summary.csv`에서 전략별/시장별 D+5, D+20, D+60의 다음 값을 비교합니다.

```text
signal_count
complete_count
avg_return_pct
median_return_pct
win_rate_pct
std_return_pct
q25_return_pct
q75_return_pct
```

Phase 10에서는 아직 어떤 실험 threshold도 ACTIVE_FILTER로 승격하지 않습니다. 결과가 충분히 쌓인 뒤 17번 Threshold Optimizer와 18번 Ablation Backtest에서 검증합니다.
