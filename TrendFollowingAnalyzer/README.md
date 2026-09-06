# TrendFollowingAnalyzer

추세추종 강의의 매매 의사결정을 독립 Analyzer로 구현합니다.

## 개발 로드맵

1. 프로젝트 뼈대 ✅
2. MA50 / MA150 ✅
3. Stage Detector ✅
4. Market Regime
   - 4A. 지수 vs MA150 + MA150 기울기 ✅
   - 4B. 52주 신고가 Breadth ✅
   - 4C. 전약후강 / 전강후약
   - 4D. 호재/악재 민감도
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

모든 규칙은 `rule_catalog.csv`에 출처와 사용 상태를 기록합니다.

- `LECTURE_CORE`: 강의에 직접 나온 원칙
- `EXPERIMENTAL`: 성능 개선 가능성을 보고 추가한 규칙
- `ACTIVE_FILTER`: 현재 후보 판정에 실제 사용
- `BACKTEST_ONLY`: 값은 저장하지만 후보 제거에는 사용하지 않음
- `PLANNED`: 강의에 있지만 아직 구현하지 않은 규칙

### 현재 ACTIVE_FILTER

- 종목 `close > MA150` + `MA150 slope > 0` → `STAGE_2`
- 시장 지수 `close > MA150` + `MA150 slope > 0` → `BULL`
- `STAGE_2 AND BULL` → `lecture_core_pass=True`

### 현재 BACKTEST_ONLY

- `MA150 slope >= 0.30%`
- 시장 `MA50 > MA150`
- 시장의 MA150 이격도
- 52주 신고가 Breadth
- 52주 신저가 Breadth / 신고가-신저가 spread
- Breadth 5일/20일 변화량 및 방향

이 값들은 후보를 제거하지 않으며 Range/Ablation Backtest 후에만 승격합니다.

## Stage 규칙

- `STAGE_2`: 종가 > MA150 + MA150 slope > 0
- `STAGE_4`: 종가 < MA150 + MA150 slope < 0
- `STAGE_1/3`: 최근 확정 Stage 4/2 문맥을 이용한 전환 분류
- `INSUFFICIENT`: 계산 데이터 부족

Stage 1/3 전환 방식은 구현상 휴리스틱이므로 별도 검증 대상입니다.

## Market Regime 4A

강의의 30주 이동평균선을 일봉 MA150으로 근사합니다.

- `BULL`: 지수 > MA150 AND MA150 slope > 0
- `BEAR`: 지수 < MA150 AND MA150 slope < 0
- `NEUTRAL`: 위치/기울기가 서로 엇갈리거나 평탄
- `INSUFFICIENT`: 데이터 부족

`BULL/NEUTRAL/BEAR` 3단계 이름 자체는 Analyzer 구현을 위한 정형화입니다.

## 52주 신고가 Breadth 4B

강의에서 시장 체력을 판단하는 두 번째 요소인 `52주 신고가 비율`을 수집합니다.

현재 구현은 다음 원칙을 지킵니다.

- Top100 후보가 아닌 **KOSPI/KOSDAQ 전체 point-in-time snapshot** 사용
- 252개 유효 거래일 기록이 있는 종목만 52주 분모에 포함
- 신규상장/데이터 부족 종목 때문에 분모가 왜곡되지 않도록 `coverage_ratio` 저장
- 공통 snapshot이 종가를 제공하므로 현재는 **52주 종가 신고가 proxy**
- 따라서 강의의 개념은 `LECTURE_CORE`지만 이 측정값은 아직 `BACKTEST_ONLY`

저장값:

```text
market_breadth_universe_count
market_breadth_eligible_count
market_breadth_coverage_ratio
market_new_high_52w_count
market_new_low_52w_count
market_new_high_52w_ratio
market_new_low_52w_ratio
market_new_high_low_spread
market_breadth_5d_avg
market_breadth_20d_avg
market_breadth_5d_change
market_breadth_20d_change
market_breadth_direction
```

`breadth_direction`은 `IMPROVING / WEAKENING / MIXED / INSUFFICIENT`이며 구현상 실험 지표입니다.

첫 실행은 약 272거래일 × KOSPI/KOSDAQ의 전체시장 snapshot을 준비하므로 시간이 걸릴 수 있습니다. 각 일자 snapshot은 공통 MarketData 캐시에 저장되어 이후 실행에서는 재사용됩니다.

## 출력

```text
results/<YYYYMMDD>/
├─ stage_market_screen.csv
├─ stage_screen.csv
├─ stage2_candidates.csv
├─ lecture_core_candidates.csv
├─ market_breadth_summary.csv
└─ rule_catalog.csv
```

- `stage2_candidates.csv`: 종목 추세 조건만 통과
- `lecture_core_candidates.csv`: 종목 Stage 2 + 해당 시장 BULL까지 통과
- `market_breadth_summary.csv`: KOSPI/KOSDAQ 각각의 52주 Breadth 측정값
- Breadth/Experimental 조건은 현재 어떤 후보 CSV에서도 제거 조건으로 사용하지 않습니다.

## 실행

```bat
run_screen.bat
```

또는:

```bash
python main.py --date 20260904 --top-n 100
```

## 테스트

```bash
python -m pytest tests -q
```

## 향후 백테스트 원칙

새 규칙은 바로 실전 필터로 넣지 않습니다.

1. 값 저장
2. Range Backtest
3. 조건 없음 vs 조건 있음 Ablation
4. 유효할 경우 Threshold Optimizer
5. 기간/시장 Regime 안정성 확인
6. 최종 ACTIVE_FILTER 승격

Breadth 예시는 다음처럼 비교합니다.

```text
A. MA150 시장 필터만
B. A + 52주 신고가 비율 수준
C. A + 52주 신고가 비율 5일 개선
D. A + 신고가-신저가 spread
```

최고 한 점만 고르지 않고 인접 임계값과 여러 시장 구간에서 성능이 유지되는지 확인합니다.
