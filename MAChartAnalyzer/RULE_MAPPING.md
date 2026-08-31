# MAChartAnalyzer V3 강의 규칙 매핑

기준 자료: 사용자가 제공한 이동평균 매매 강의 자막.

강의에서 직접 설명한 구조와 백테스트를 위해 수치화한 구현값을 구분합니다.

## 1. 강의에서 가져온 핵심 구조

- **방향 먼저**: 장기 이동평균의 위치와 기울기로 매수 방향을 정한다.
- **단기 MA로 타점**: 장기 방향이 맞는 상태에서 단기 MA 눌림/재상승을 본다.
- **돌파 확인**: 장대 양봉, MA 완전 분리, 직전 고점 몸통 돌파를 확인한다.
- **Squeeze**: 압축 자체보다 장기 방향과 같은 탈출을 기다린다.
- **횡보 회피**: 가격/이평 교차 반복 구간에서는 추세매매를 쉬고 박스 이탈을 기다린다.
- **박스 돌파와 Retest**: 박스 돌파 후 상단을 다시 확인해 지지하는 구간은 추가 매수 근거가 된다.
- **리스크 관리**: 진입봉 저가와 단기 MA 훼손을 손절/청산 근거로 사용한다.

## 2. V2에서 확립한 신호 규칙

### BOX_BREAKOUT
현재봉이 과거 박스 상단을 새로 강하게 돌파해야 한다. V1 성과에서 가장 안정적이어서 핵심 CONFIRMED로 유지한다.

### BOX_RETEST_CONFIRMED
현재 돌파봉 자체가 Retest가 될 수 없다. 과거 1~5봉 전 실제 돌파가 먼저 존재하고, 이후 해당 레벨로 되돌아와 종가가 레벨 위를 유지할 때만 인정한다.

### Pullback
일반 `PULLBACK_RECLAIM`은 WATCH다. `Long_Bull_Body + Detached_Above_MA`가 함께 확인된 `PULLBACK_STRONG_CONFIRMATION`만 CONFIRMED 가능하다.

### Squeeze
`SQUEEZE_SETUP_WATCH`, `SQUEEZE_BREAKOUT_WATCH`로만 사용한다.

## 3. V3에서 cooldown을 제거한 이유

V2에서는 같은 종목의 확정 신호를 10거래일 동안 다시 거래하지 않았다.

그러나 이 방식은:

```text
BOX_BREAKOUT -> 1~5봉 후 BOX_RETEST_CONFIRMED
```

같은 중요한 후속 타점을 제거할 수 있다.

Retest는 단순 중복 신호가 아니라 **기존 포지션에 추가 진입할 근거**이므로 V3에서는 time-based cooldown을 매매 판단에서 사용하지 않는다.

## 4. V3 3단계 분할진입

계획자금 100% 기준:

### 1차 34%
포지션이 없을 때 첫 `STRONG_CONFIRMED / CONFIRMED` 발생.

### 2차 33%
1차 보유 중 `BOX_RETEST_CONFIRMED` 발생.

### 3차 33%
2차까지 체결된 이후 새로운 다음 확인 중 하나가 발생:

- `BOX_BREAKOUT`
- `PRIOR_HIGH_BREAKOUT`
- `PULLBACK_STRONG_CONFIRMATION`

## 5. 중복 방지 방식

cooldown 대신 Position 상태를 사용한다.

```text
포지션 없음 -> Stage1 가능
Stage1 보유 -> Stage2 조건만 가능
Stage2 보유 -> Stage3 조건만 가능
Stage3 보유 -> 추가 진입 없음
```

동일 단계 반복 신호는 `IGNORED_REPEAT_OR_STAGE_NOT_READY`로 남기고 매수하지 않는다.

## 6. 진입가격과 Stop

모든 신호는 종가 확정 후 **다음 거래일 시가**에 체결한다.

1차 Stop은 1차 신호봉 저가다.

2차/3차 추가진입 때:

```text
new_stop = max(old_stop, new_signal_low)
```

을 적용한다. 추가매수 때문에 보호 Stop을 다시 아래로 넓히지 않는다.

## 7. 청산

1. 시가가 Position Stop 아래로 Gap 하락 -> 시가 청산
2. 장중 Position Stop 터치 -> Stop 가격 청산
3. 종가가 단기 MA 아래 -> 종가 청산
4. 최대 보유기간 -> TIME EXIT

## 8. 백테스트 수익률 정의

### Trade_Return_Pct
실제로 투입된 Stage 자금만 기준으로 계산한다.

### Portfolio_Return_Pct
계획자금 100% 중 아직 투입되지 않은 현금은 0% 수익으로 남겨 두고 계산한다.

예: 1차 34%만 체결되고 해당 Stage가 +10% 수익이면 전체 계획자금 기준 수익은 약 +3.4%다.

## 9. 강의에 숫자가 없어 구현값으로 둔 항목

- MA 수평 허용폭
- Squeeze 간격/압축비율
- 장대봉 배수
- MA touch 허용오차
- 횡보 교차 횟수
- 박스 돌파 buffer
- Retest 허용폭
- 추격 이격 제한
- 34/33/33 진입 비중

이 값들은 강의 원문 숫자로 주장하지 않으며 백테스트를 위한 configurable engineering parameter다.

## 10. 구현하지 않은 부분

강의 후반의 `세력 지표 / 중요 가격구간 자동 탐지`는 정확한 계산식이 공개되지 않았다.

현재 Box는 최근 가격 고저 범위 기반 구현이며 강의의 세력 지표와 동일하다고 간주하지 않는다.
