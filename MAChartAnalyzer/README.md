# MAChartAnalyzer V2

사용자가 제공한 이동평균 매매 강의를 기반으로 만든 **독립 BUY 판단 Analyzer**입니다.

`KJBChartAnalyzer`, `SwingChartProbabilityAnalyzer`와 점수를 합치지 않으며 각 Analyzer의 신호는 독립적으로 유지합니다.

## 전략 구조

`Direction -> Setup -> Confirmation -> Sideways Filter -> Risk -> Trade Management`

- 장기 방향: 200MA 위치 + 기울기
- 단기 타점: 단기 MA(기본 20) 눌림/재돌파
- Squeeze: 단기/장기 MA 압축을 Setup으로 감시
- 핵심 매수: 상승 방향에서의 강한 박스 상단 돌파
- 돌파 확인: 장대 양봉 / MA와 캔들 완전 분리 / 직전 고점 몸통 돌파
- 횡보 회피: 가격/이평의 반복 교차
- 실제 Retest: 돌파 당일이 아니라 과거 1~5봉 전 박스 돌파 레벨을 다시 지지하는지 확인
- 추격 방지: 단기 MA 대비 과도한 이격 제한
- 위험 신호: 장기 MA의 명확한 하향 훼손

강의 규칙과 코드 매핑은 `RULE_MAPPING.md` 참고.

## V2에서 바뀐 점

V1 기간 백테스트 결과를 바탕으로 다음을 수정했습니다.

1. `BOX_BREAKOUT`을 핵심 CONFIRMED 트리거로 유지.
2. 일반 `PULLBACK_RECLAIM`은 WATCH로 강등.
3. Pullback은 **장대 양봉 + MA 위 완전 분리**가 함께 확인되어야 `PULLBACK_STRONG_CONFIRMATION`으로 CONFIRMED 가능.
4. `SQUEEZE_BREAKOUT`은 단독 매수신호가 아니라 WATCH Setup으로 사용.
5. 20봉 박스 돌파와 20봉 전고점 돌파의 중복 점수 제거.
6. 같은 돌파봉이 `Box_Retest_Hold`로 동시에 잡히던 오류 제거.
7. Retest는 **과거 1~5봉 전 실제 돌파 이후** 현재 가격이 그 레벨을 다시 확인하고 지지해야 인정.
8. 상태를 `STRONG_CONFIRMED / CONFIRMED / WATCH / REJECTED`로 세분화.
9. 기간 백테스트의 진입가격을 신호일 종가가 아니라 **D+1 시가**로 변경.
10. 실제 포지션 시뮬레이션 추가: `신호봉 저가 손절 -> 단기 MA 종가 이탈 -> 최대 보유기간 청산`.
11. 같은 종목 확정신호는 기본 10거래일 cooldown 적용.
12. 루트 통합 백테스트에서는 **각 신호일 당시 KOSPI+KOSDAQ 최근 20거래일 평균 거래대금 TOP N** point-in-time Universe 사용.

## 상태 판정

### STRONG_CONFIRMED

확정 매수 Trigger를 충족하고 기본적으로:

- `Score >= 80`
- `Timing_Score >= 70`

인 강한 후보입니다.

### CONFIRMED

장기 상승 방향이 유효하고 다음 중 하나의 확정 Trigger가 있으며 추격위험/횡보 차단 조건을 통과한 후보입니다.

- `BOX_BREAKOUT`
- `BOX_RETEST_CONFIRMED`
- `PULLBACK_STRONG_CONFIRMATION`
- 강한 캔들 확인을 동반한 `PRIOR_HIGH_BREAKOUT`

기본 최소값:

- `Score >= 70`
- `Timing_Score >= 50`

### WATCH

방향은 유효하지만 확정 매수까지 한 단계 부족한 Setup입니다.

- `SQUEEZE_SETUP_WATCH`
- `SQUEEZE_BREAKOUT_WATCH`
- `PULLBACK_RECLAIM_WATCH`
- 기타 추세 유지 + 확인 대기

### REJECTED

대표적으로:

- 장기 매수 방향 미확인
- 200MA 명확한 하향 훼손
- 반복 교차 횡보인데 박스 이탈/Retest 확인 없음
- 추격 이격 과다
- 진입조건 미완성

## 일일 스크리닝

```bat
MAChartAnalyzer\run_screen.bat 100
```

프로젝트 루트의 전체 스크리닝:

```bat
run_all_screen.bat
```

결과:

```text
MAChartAnalyzer/results/YYYYMMDD/
  scan_results.csv
  candidates.csv
  ma_candidates.xlsx
```

## 기간 백테스트

MA만 단독 실행:

```bat
MAChartAnalyzer\run_ma_range.bat 20260101~20260821 100 market_cap
```

KJB/Swing/MA를 동일한 point-in-time Universe로 실행:

```bat
run_combined_range.bat 20260101~20260821 100
```

루트 통합 실행에서는 `TOP_N=100`이면 각 신호일 당시:

- KOSPI + KOSDAQ
- 최근 20거래일 평균 거래대금
- 상위 100종목

만 평가합니다. 현재 시점의 시가총액 TOP100을 과거 전체 기간에 소급 적용하지 않습니다.

## 기간 결과

```text
MAChartAnalyzer/results/range_YYYYMMDD_YYYYMMDD/
  range_all_results.csv
  range_candidates.csv
  trade_events.csv
  ma_range_backtest.xlsx
```

`ma_range_backtest.xlsx`에는 다음 시트가 생성됩니다.

- `AllResults`: 모든 일별 판정
- `Candidates`: cooldown 반영 확정후보 + WATCH
- `TradeEvents`: 실제 매매 시뮬레이션 대상
- `Summary`: 상태별 통계
- `TradeSummary`: 신호별 실제 매매 성과
- `Config`: 사용한 임계값/실행조건

## 실제 매매 백테스트 기준

확정 신호일을 D0라고 할 때:

1. **D+1 시가 진입**
2. 신호봉 저가 아래로 Gap 발생 시 D+1 이후 해당 시가에서 손절
3. 장중 신호봉 저가 이탈 시 신호봉 저가 가격으로 손절 처리
4. 그 전에 손절되지 않았다면 종가가 단기 MA 아래로 내려오는 첫 날 종가 청산
5. 끝까지 청산되지 않으면 `forward_bars` 시점 종가로 TIME EXIT

주요 필드:

- `Entry_Price_D1_Open`
- `Cooldown_Eligible`
- `Trade_Return_Pct`
- `Trade_Exit_Reason`
- `Trade_Holding_Bars`
- `Trade_MFE_Pct`
- `Trade_MAE_Pct`
- `Universe_Rank`
- `Avg_Trading_Value_20D`

기존 신호일 종가 기준 D+N 성과도 비교용으로 `Signal_D+N_Close_Return_Pct`에 남겨 둡니다.

## 주의

강의 자동자막은 단기 이동평균 값이 `20`, `22`처럼 혼재합니다. 구현 기본값은 20이며 `config.py`에서 변경할 수 있습니다.

또한 Squeeze 간격, 장대봉 배수, 횡보 교차 횟수 등의 숫자는 강의에서 직접 제시된 값이 아니라 정성적 설명을 백테스트 가능하게 만든 구현 파라미터입니다.

강의 후반의 이른바 `세력 지표`는 정확한 산식이 공개되지 않았으므로 임의 구현하지 않았습니다.
