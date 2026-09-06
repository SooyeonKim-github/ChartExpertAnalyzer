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
6. Prior Advance
7. Generic Base Detector
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

`LECTURE_CORE`와 구현상 추가한 `EXPERIMENTAL`을 구분하고, 검증 전 지표는 `BACKTEST_ONLY`로 저장만 합니다. 현재 ACTIVE_FILTER는 종목 `STAGE_2`와 해당 시장 `BULL`뿐입니다. Breadth, Intraday Proxy, RS는 아직 후보를 제거하지 않습니다.

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

라벨은 `WEAK_MARKET_RESILIENT`, `CONSISTENT_OUTPERFORM`, `MIXED_OUTPERFORMANCE`, `UNDERPERFORM`, `INSUFFICIENT`를 저장합니다.

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
└─ rule_catalog.csv
```

## 실행

```bat
run_screen.bat
```

또는 `python main.py --date 20260904 --top-n 100`.

## 향후 RS 백테스트

A. Stage2 + Market BULL / B. A+RS20>0 / C. A+RS20>0+RS60>0 / D. A+RS percentile>=70 / E. >=80 / F. >=90을 비교하고, 여러 기간과 시장 국면에서 안정적인 조건만 ACTIVE_FILTER 승격을 검토합니다.
