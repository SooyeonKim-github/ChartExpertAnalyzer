# MAChartAnalyzer V2 강의 규칙 매핑

기준 자료: 사용자가 제공한 이동평균 매매 강의 자막.

강의에서 직접 설명한 구조와 백테스트를 위해 수치화한 구현 임계값을 구분합니다.

## 1. 강의에서 직접 가져온 구조

### 방향이 먼저

- 장기 이동평균 위/아래에 가격이 있는지 본다.
- 장기 이동평균의 기울기로 상승/하락 방향을 본다.
- 상승 방향이면 매수만 우선하고 방향이 불분명하면 쉬는 것이 원칙이다.

구현:

- 장기선 기본 `MA200`
- `Close > MA200` + MA200 우상향을 기본 상승 Regime으로 사용
- MA200이 수평권이고 단기 MA가 상승할 때는 전환 Regime으로 관찰

### 단기 이동평균으로 타점을 잡는다

강의는 장기 이평으로 방향을 정한 뒤 단기 이평으로 눌림과 재상승 타점을 찾는다.
자동자막의 단기 값은 20/22가 혼재하므로 구현 기본값은 20이며 설정 가능하다.

### 돌파 확인

강의에서 강조하는 확인 방식:

- 몸통이 긴 강한 캔들
- 캔들의 몸통/꼬리가 이동평균에 전혀 닿지 않는 완전 분리
- 직전 고점을 몸통 기준으로 돌파

구현 필드:

- `Long_Bull_Body`
- `Detached_Above_MA`
- `Prior_High_Breakout`

### Squeeze Play

- 단기/장기 이평 사이 공간이 좁아진다.
- 가격도 두 이평 사이에 압축된다.
- 장기 추세와 같은 방향의 탈출을 우선한다.
- 강한 장기 하락 중 역방향 돌파는 매수로 보지 않는다.

V2에서는 V1 성과를 반영해 Squeeze를 **매수 확정이 아니라 WATCH Setup**으로 사용한다.

### 눌림목

- 상승 방향 유지 중 단기 MA 부근 눌림은 매수 Setup이 될 수 있다.
- 장기 MA 명확한 하향 돌파는 정상 눌림이 아니라 추세 훼손 위험이다.

V2에서는 일반 `Pullback_Reclaim`만으로 CONFIRMED하지 않는다.
`Pullback_Reclaim + Long_Bull_Body + Detached_Above_MA`가 동시에 충족된 경우를
`Strong_Pullback_Confirmation`으로 별도 확인한다.

### 횡보 회피

- 가격↔단기 MA, 가격↔장기 MA, 단기↔장기 MA 교차가 짧은 구간에서 반복되면 횡보 위험이다.
- 횡보에서는 추세매매를 쉬고 박스 이탈을 기다린다.

### 박스 돌파와 Retest

강의에서는 횡보 박스 상단을 강하게 돌파하면 신규 추세에 대응하고,
돌파 후 상단을 다시 확인해 지지하면 추가적인 매수 근거로 본다.

V2 구현:

- `Box_Breakout`: 현재봉이 직전 박스 상단을 새로 강하게 돌파해야 함.
- `Box_Retest_Hold`: **현재 돌파봉 자체가 아니라 과거 1~5봉 전 실제 돌파**가 먼저 존재해야 함.
- 이후 현재봉 저가가 당시 돌파 레벨 근처까지 내려오고 과도하게 무너지지 않은 채 종가가 레벨 위를 유지해야 Retest로 인정.

## 2. V1 백테스트에서 확인된 문제와 V2 조정

### BOX_BREAKOUT

V1에서 가장 안정적인 성과를 보여 핵심 CONFIRMED 신호로 유지한다.

### PULLBACK_RECLAIM

V1에서는 단독 CONFIRMED가 많았으나 중기 성과가 약했다.
V2에서는 일반 Pullback을 WATCH로 두고 강한 양봉/완전 분리 확인을 추가한다.

### SQUEEZE_BREAKOUT

V1의 확정 표본이 작고 성과가 불안정했다.
V2에서는 Squeeze와 Squeeze Breakout 모두 Setup/관찰 신호로 취급한다.

### 중복 점수 제거

V1에서는 `prior_high_lookback_bars=20`, `box_lookback_bars=20`이라
박스 상단 돌파가 사실상 같은 20봉 고점 돌파를 의미하면서 둘 다 점수를 받을 수 있었다.

V2에서는:

- `Box_Breakout=True`이면 Box 점수만 부여
- Box가 아니면서 Prior High 돌파일 때만 Prior High 점수 부여

따라서 같은 가격 이벤트를 두 번 평가하지 않는다.

### 가짜 Retest 제거

V1의 `Box_Retest_Hold`는 돌파 당일 저가가 Box High 근처에 있기만 해도 True가 될 수 있었다.
V2에서는 과거 돌파가 먼저 있어야 하므로 동일 봉 Breakout+Retest 동시 판정이 불가능하다.

## 3. V2 상태 판정

### STRONG_CONFIRMED

확정 Trigger + 방향/리스크 조건을 통과하고:

- `Score >= 80`
- `Timing_Score >= 70`

### CONFIRMED

다음 중 하나의 확정 Trigger가 필요하다.

- `BOX_BREAKOUT`
- `BOX_RETEST_CONFIRMED`
- `PULLBACK_STRONG_CONFIRMATION`
- 강한 확인을 동반한 `PRIOR_HIGH_BREAKOUT`

추가 기본조건:

- 장기 매수 방향 유효
- 횡보 무돌파 상태가 아님
- Chase Risk가 아님
- `Score >= 70`
- `Timing_Score >= 50`

### WATCH

장기 방향은 유효하지만 아직 확정 진입이 아닌 상태.

대표:

- `SQUEEZE_SETUP_WATCH`
- `SQUEEZE_BREAKOUT_WATCH`
- `PULLBACK_RECLAIM_WATCH`
- `TREND_OK_WAIT_CONFIRMATION`

### REJECTED

대표:

- `LONG_DIRECTION_NOT_CONFIRMED`
- `LONG_MA_DECISIVE_BREAKDOWN`
- `SIDEWAYS_NO_TRADE`
- `CHASE_RISK`
- `ENTRY_CONDITIONS_INCOMPLETE`

## 4. 실제 백테스트 규칙

V1의 단순 신호일 종가 기준 D+N 비교를 보완한다.

### 진입

- 신호일 = D0
- 실제 진입 = **D+1 시가**

### 청산 우선순위

1. D+1 이후 시가가 신호봉 저가 아래로 Gap 하락하면 해당 시가 손절.
2. 장중 신호봉 저가를 터치/이탈하면 신호봉 저가 가격으로 손절 처리.
3. 종가가 단기 MA 아래로 내려오면 해당 종가 청산.
4. 위 조건이 없으면 최대 `forward_bars`에서 종가 TIME EXIT.

### Cooldown

같은 종목에서 확정 신호가 반복되어 통계가 과도하게 중복되는 것을 줄이기 위해
기본 10거래일 cooldown을 적용한다.

`Cooldown_Eligible=1`인 STRONG/CONFIRMED만 `TradeEvents`와 통합 확정후보에 사용한다.

## 5. Point-in-time Universe

루트 `run_combined_range.bat` 실행 시 현재 시점의 TOP100을 과거 전체 기간에 소급하지 않는다.

각 신호일 당시:

- KOSPI + KOSDAQ
- 최근 20거래일 평균 거래대금
- 상위 TOP N

membership을 생성한다.

KJB/Swing은 기간 중 포함된 종목 union을 먼저 분석한 뒤 각 날짜 membership으로 필터하고,
MA V2는 분석 단계에서 날짜+ticker membership을 직접 적용한다.

이렇게 하면 Analyzer 간 Universe 조건을 동일하게 유지하면서 미래 시점 Universe 정보가 과거 신호 선택에 들어가는 문제를 줄인다.

## 6. 구현 임계값과 강의 원문을 구분해야 하는 항목

강의에서 아래 숫자는 직접 제시하지 않았다. 따라서 백테스트용 구현 파라미터일 뿐 강의 원문 숫자가 아니다.

- MA 기울기의 수평 허용폭
- Squeeze 최대 간격 및 압축 비율
- 장대봉 배수
- 단기 MA touch 허용오차
- 반복 교차 횟수
- 박스 돌파 buffer
- Retest 허용폭/최대 하향 이탈폭
- MA20 추격 이격 제한
- Score/Timing 상태 임계값
- Cooldown 기간

모두 `config.py`에서 조정 가능하다.

## 7. 의도적으로 구현하지 않은 부분

강의 후반의 이른바 **세력 지표 / 중요 가격구간 자동 탐지**는 정확한 계산식이 공개되지 않는다.
따라서 임의로 거래량 매물대 등으로 대체하지 않았다.

현재 Box는 최근 가격 고저 범위 기반 구현이며 강의의 세력 지표와 동일한 것으로 간주하지 않는다.
