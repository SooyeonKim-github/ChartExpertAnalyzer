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
   - 4D. 호재/악재 민감도 ⏳
5. Relative Strength
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

## Rule Provenance 원칙

모든 규칙은 `rule_catalog.csv`에 출처와 사용 상태를 기록합니다. `LECTURE_CORE`는 강의 원칙, `EXPERIMENTAL`은 구현상 추가, `ACTIVE_FILTER`는 실제 필터, `BACKTEST_ONLY`는 기록만, `PLANNED`는 미구현입니다.

현재 ACTIVE_FILTER는 종목 `close > MA150 + slope > 0`의 STAGE_2와 시장 지수 `close > MA150 + slope > 0`의 BULL뿐입니다. Breadth와 Intraday Proxy는 후보를 제거하지 않습니다.

## 4C 전약후강 / 전강후약

지수 일봉 OHLC를 이용해 Daily Proxy로 근사합니다. 일봉만으로는 고가/저가 발생 순서를 알 수 없으므로 실제 오전/오후 순서를 의미하지 않습니다.

저장값: `gap_return_pct`, `open_close_return_pct`, `close_return_pct`, `close_location_value`, `recovery_strength_pct`, `fade_strength_pct`, `experimental_intraday_strength_score`.

라벨은 `WEAK_OPEN_STRONG_CLOSE`, `STRONG_OPEN_WEAK_CLOSE`, `STRONG_CLOSE`, `WEAK_CLOSE`, `MIXED`, `INSUFFICIENT`입니다. 기본 실험 임계값은 Strong Close=`CLV >= 0.70 AND close > open`, Weak Close=`CLV <= 0.30 AND close < open`이며 강의 수치가 아니므로 EXPERIMENTAL+BACKTEST_ONLY입니다.

최근 5일/20일의 전약후강·전강후약·Strong Close·Weak Close 비율과 `intraday_direction=IMPROVING/WEAKENING/MIXED/INSUFFICIENT`를 저장합니다. Recovery/Fade/복합점수도 저장하지만 V1 의사결정에는 쓰지 않습니다.

## 4D 뉴스 반응 설계 방향

핵심은 뉴스 감성 자체보다 **시장이 악재를 흡수하는지, 악재에 민감하게 무너지는지**를 측정하는 것입니다.

1. 시장 영향 뉴스 이벤트 수집
2. `POSITIVE / NEGATIVE / NEUTRAL` 분류
3. 발표 시각을 기준으로 같은 거래일/다음 거래일에 정렬
4. KOSPI/KOSDAQ의 당일/익일 수익률, 시가 갭, 종가 회복, CLV, 변동성/거래대금 반응 측정
5. `NEGATIVE_NEWS_ABSORBED`, `NEGATIVE_NEWS_SENSITIVE`, `POSITIVE_NEWS_RESPONSIVE`, `POSITIVE_NEWS_IGNORED` 등으로 반응 분류
6. 최근 5일/20일 absorption/sensitivity 비율 계산
7. 초기에는 전부 BACKTEST_ONLY

뉴스 중요도·감성모델·반응시간창은 구현상 추가 요소이므로 Ablation/Threshold 검증 전까지 ACTIVE_FILTER로 사용하지 않습니다.

## 출력

`results/<YYYYMMDD>/` 아래 `stage_market_screen.csv`, `stage2_candidates.csv`, `lecture_core_candidates.csv`, `market_breadth_summary.csv`, `market_intraday_summary.csv`, `rule_catalog.csv`가 생성됩니다.

## 실행

```bat
run_screen.bat
```

또는 `python main.py --date 20260904 --top-n 100`.

## 백테스트 원칙

A. MA150 시장 필터만 / B. A+Breadth / C. A+Intraday / D. A+Breadth+Intraday를 비교하고, 유효한 경우에만 Threshold Optimizer 후 ACTIVE_FILTER로 승격합니다.
