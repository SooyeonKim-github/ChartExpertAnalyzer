# MAChartAnalyzer V3

사용자가 제공한 이동평균 매매 강의를 기반으로 만든 **독립 BUY 판단 Analyzer**입니다.

`KJBChartAnalyzer`, `SwingChartProbabilityAnalyzer`와 점수를 합치지 않으며 각 Analyzer의 신호는 독립적으로 유지합니다.

## 전략 구조

`Direction -> Setup -> Confirmation -> Sideways Filter -> Risk -> Stateful Position Management`

- 장기 방향: 200MA 위치 + 기울기
- 단기 타점: 단기 MA(기본 20) 눌림/재돌파
- Squeeze: 단기/장기 MA 압축을 WATCH Setup으로 감시
- 핵심 매수: 상승 방향에서의 강한 박스 상단 돌파
- 실제 Retest: 과거 1~5봉 전 박스 돌파 레벨 재지지
- Pullback: 일반 눌림은 WATCH, 강한 재상승 확인만 CONFIRMED
- 추격 방지: 단기 MA 대비 과도한 이격 제한
- 청산: 보호 Stop -> MA20 종가 이탈 -> 최대 보유기간

강의 규칙과 코드 매핑은 `RULE_MAPPING.md` 참고.

## V3 핵심 변경

V2 최신 백테스트에서 10거래일 cooldown이 좋은 `BOX_RETEST_CONFIRMED` 신호를 많이 제거한 문제가 확인되어, **매매 의사결정에서 cooldown을 완전히 제거**했습니다.

대신 같은 종목을 독립 신호 여러 개로 반복 매수하지 않고 **하나의 Position 상태**로 관리합니다.

### 3단계 분할진입

계획자금 100%를 다음처럼 나눕니다.

1. **1차 34%**: 포지션이 없을 때 첫 `STRONG_CONFIRMED / CONFIRMED` 신호
2. **2차 33%**: 1차 보유 중 `BOX_RETEST_CONFIRMED`
3. **3차 33%**: 2차까지 보유한 뒤 새로운 `BOX_BREAKOUT / PRIOR_HIGH_BREAKOUT / PULLBACK_STRONG_CONFIRMATION`

같은 단계의 반복 신호는 `IGNORED_REPEAT_OR_STAGE_NOT_READY`로 기록하고 추가매수하지 않습니다.

모든 진입은 신호가 확정된 **다음 거래일 시가**에 체결합니다.

추가진입 시 보호 Stop은 새 신호봉 저가를 반영하되 기존 Stop보다 낮추지 않습니다.

```text
new_stop = max(old_stop, new_signal_low)
```

즉 추가매수한다고 손절선을 다시 아래로 넓히지 않습니다.

## 상태 판정

### STRONG_CONFIRMED

- 확정 Trigger 존재
- `Score >= 80`
- `Timing_Score >= 70`

### CONFIRMED

확정 Trigger:

- `BOX_BREAKOUT`
- `BOX_RETEST_CONFIRMED`
- `PULLBACK_STRONG_CONFIRMATION`
- 강한 캔들 확인을 동반한 `PRIOR_HIGH_BREAKOUT`

기본 최소값:

- `Score >= 70`
- `Timing_Score >= 50`

### WATCH

- `SQUEEZE_SETUP_WATCH`
- `SQUEEZE_BREAKOUT_WATCH`
- `PULLBACK_RECLAIM_WATCH`
- 기타 추세 유지 + 확인 대기

### REJECTED

- 장기 매수 방향 미확인
- 200MA 명확한 하향 훼손
- 반복 교차 횡보
- 추격 이격 과다
- 진입조건 미완성

## 일일 스크리닝

```bat
MAChartAnalyzer\run_screen.bat 100
```

전체 스크리닝:

```bat
run_all_screen.bat
```

일일 스크리닝은 신호 자체를 출력합니다. 실제 1/2/3차 진입 여부는 보유 Position 상태와 함께 판단해야 합니다.

## 기간 백테스트

MA 단독:

```bat
MAChartAnalyzer\run_ma_range.bat 20260101~20260821 100 market_cap
```

KJB/Swing/MA 통합 point-in-time Universe:

```bat
run_combined_range.bat 20260101~20260821 100
```

루트 통합 실행에서는 각 신호일 당시 KOSPI+KOSDAQ 최근 20거래일 평균 거래대금 TOP N만 사용합니다.

## 기간 결과

```text
MAChartAnalyzer/results/range_YYYYMMDD_YYYYMMDD/
  range_all_results.csv
  range_candidates.csv
  position_entries.csv
  trade_events.csv
  ma_range_backtest.xlsx
```

### `range_all_results.csv`

모든 일별 신호와 다음 Position 필드가 추가됩니다.

- `Position_ID`
- `Position_Action`
- `Entry_Stage`
- `Entry_Allocation_Pct`
- `Entry_Fill_Date`
- `Entry_Fill_Price`

### `position_entries.csv`

실제로 체결된 1/2/3차 진입을 한 행씩 저장합니다.

### `trade_events.csv`

**한 Position당 한 행**입니다. 여러 신호를 별도 거래로 중복 계산하지 않습니다.

주요 필드:

- `Filled_Stages`
- `Invested_Weight_Pct`
- `Avg_Entry_Price`
- `Stage1/2/3_Entry_Date`
- `Stage1/2/3_Entry_Price`
- `Trade_Return_Pct`: 실제 투입된 자금만 기준으로 계산한 수익률
- `Portfolio_Return_Pct`: 미투입 현금을 0% 수익으로 포함한 계획자금 100% 기준 수익률
- `Trade_Exit_Reason`
- `Trade_Holding_Bars`
- `Trade_MFE_Pct`
- `Trade_MAE_Pct`

## 실제 포지션 청산

우선순위:

1. 시가가 현재 Position Stop 아래로 Gap 하락 -> 시가 청산
2. 장중 현재 Position Stop 터치/이탈 -> Stop 가격 청산
3. 종가가 MA20 아래로 내려옴 -> 종가 청산
4. 최대 `forward_bars` 도달 -> TIME EXIT

추가진입 시 Stop은 위로만 조정되며 절대 완화하지 않습니다.

## V2와 다른 점

V2:

```text
확정 신호 -> 10봉 cooldown -> 각 신호를 독립 Trade로 평가
```

V3:

```text
확정 신호 -> cooldown 없음
         -> 포지션 없으면 1차
         -> Retest면 2차
         -> 재돌파/강한 눌림이면 3차
         -> 동일 단계 반복은 무시
         -> 한 Position으로 통합 평가
```

즉 **시간으로 신호를 막는 대신 Position 상태와 신호 의미로 중복을 제어**합니다.

## 주의

강의 자동자막의 단기 이동평균 값은 `20`, `22`처럼 혼재합니다. 기본값은 20이며 설정 가능합니다.

Squeeze 간격, 장대봉 배수, 횡보 교차 횟수 등 강의에서 숫자로 제시되지 않은 값은 백테스트를 위한 구현 파라미터입니다.

강의 후반의 이른바 `세력 지표`는 정확한 산식이 공개되지 않아 임의 구현하지 않았습니다.
