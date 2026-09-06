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
8. Volume Contraction
9. Breakout Detector
10. V1 Backtest
11. VCP
12. Cup With Handle
13. Initial Stop
14. High Volume Reversal
15. MA50 / MA150 Trend Exit
16. Score
17. Threshold Optimizer
18. Ablation Backtest

## 원칙

`LECTURE_CORE`와 구현상 추가한 `EXPERIMENTAL`을 구분하고, 검증 전 지표는 `BACKTEST_ONLY`로 저장만 합니다. 현재 ACTIVE_FILTER는 종목 `STAGE_2`와 해당 시장 `BULL`뿐입니다. Breadth, Intraday Proxy, RS, Prior Advance, Generic Base는 아직 후보를 제거하지 않습니다.

## Phase 5 - Relative Strength

강의의 RS는 RSI가 아니라 **종목이 시장보다 얼마나 강한지**를 뜻합니다. 특히 시장이 조정/횡보할 때 덜 빠지거나 오르는 종목을 선도주 후보로 보는 원칙을 구현합니다.

현재 수치화 방식:

```text
stock_factor_N = stock_close_today / stock_close_N_sessions_ago
benchmark_factor_N = benchmark_close_today / benchmark_close_N_sessions_ago
RS_N = (stock_factor_N / benchmark_factor_N - 1) * 100
```

- KOSPI 종목은 KOSPI 지수, KOSDAQ 종목은 KOSDAQ 지수와 비교
- 20일 / 60일 RS 저장
- 동일 시장의 당일 거래대금 Top-N 스크린 유니버스 안에서 20/60일 percentile 계산
- `rs_percentile_composite`는 20/60일 percentile 단순 평균
- `experimental_min_percentile=80` 여부도 기록

강의에는 20/60일, percentile 80 같은 숫자가 없으므로 이 수치들은 모두 EXPERIMENTAL+BACKTEST_ONLY입니다.

## Phase 6 - Prior Advance

강한 베이스는 임의의 바닥이 아니라 **선행 상승 이후 만들어져야 한다**는 강의 원칙을 기록합니다.

- Base가 아직 없으면 최근 20거래일을 임시 Base proxy로 제외
- Base가 탐지되면 실제 `base_start_date` 이전으로 Prior Advance를 재계산
- 이전 120거래일에서 시간순 저점→고점 최대 상승을 측정
- `prior_advance_pct`, 상승 지속일, MA150 확장도, 고점→anchor 거래일을 저장
- 30% 기준은 강의에 없는 실험값이므로 BACKTEST_ONLY

## Phase 7 - Generic Base Detector V1

강의의 핵심 흐름인 `강한 선행 상승 → 베이스 → 돌파 대기` 중 **가격 베이스 구조**를 구현합니다. 아직 거래량 수축은 포함하지 않으며 Phase 8에서 별도로 추가합니다.

Generic Base V1은 현재 시점까지만 사용해 최근 저항대 시작점부터 현재까지의 후보를 찾습니다.

```text
기본 탐색창                 15~60 거래일
Base 최대 깊이              35%
현재가의 Base 고점 이격     -12% 이내
시작 저항대 허용오차         3%
Loose 판정 ratio             1.25
```

위 숫자는 전부 EXPERIMENTAL+BACKTEST_ONLY이며 ACTIVE_FILTER가 아닙니다.

저장 지표:

```text
base_start_date / base_end_date
base_duration_sessions
base_high / base_low / base_depth_pct
base_current_vs_high_pct
base_atr_early_pct / base_atr_late_pct / base_atr_contraction_ratio
base_range_early_pct / base_range_late_pct / base_range_contraction_ratio
base_close_dispersion_pct
base_experimental_quality_score
```

상태:

```text
BASE_DETECTED
TOO_DEEP
TOO_LOOSE
NO_BASE
INSUFFICIENT
```

### Prior Advance와 실제 Base 연결

Base가 잡히면 Prior Advance의 anchor를 `base_start_date`로 바꾸고 다음을 추가 저장합니다.

```text
prior_advance_peak_to_base_sessions
prior_advance_drawdown_to_base_low_pct
prior_advance_retention_ratio
prior_advance_current_retention_ratio
```

`prior_advance_retention_ratio`는 선행 상승분 중 **Base 최저점에서도 얼마나 유지했는지**를 봅니다.

```text
prior low  = 100
prior peak = 200
base low   = 170

retention = (170 - 100) / (200 - 100) = 0.70
```

즉 과거 상승폭만 큰 종목과, 상승 후 고점 부근에서 건강하게 쉬는 종목을 구분하기 위한 지표입니다.

## 출력

```text
results/<YYYYMMDD>/
├─ stage_market_screen.csv
├─ stage_screen.csv
├─ stage2_candidates.csv
├─ lecture_core_candidates.csv
├─ market_breadth_summary.csv
├─ market_intraday_summary.csv
├─ relative_strength_summary.csv
├─ prior_advance_summary.csv
├─ base_summary.csv
└─ rule_catalog.csv
```

## 실행

```bat
run_screen.bat
```

또는:

```bat
python main.py --date 20260904 --top-n 100
```

## 향후 백테스트

Base V1은 바로 hard filter로 승격하지 않고 다음 bucket/ablation을 먼저 비교합니다.

- Base depth 구간
- Base duration 구간
- ATR contraction ratio
- range contraction ratio
- Prior Peak → Base freshness
- advance retention ratio
- Stage2 + Market BULL 대비 추가 수익/승률/기대값/MDD 변화

안정적으로 재현되는 구간만 Threshold Optimizer 후보로 승격합니다.
