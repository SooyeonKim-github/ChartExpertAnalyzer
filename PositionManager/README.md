# PositionManager V3

`CONFIRMED` 이후의 실제 진입, 추가매수, 손절, 트레일링, 기간청산을 Analyzer와 독립적으로 관리한다.

V3의 핵심 원칙은 **처음부터 크게 들어가지 않고, CONFIRMED 다음 거래일 시가에 소액으로 시작한 뒤 강도가 다시 확인될 때만 비중을 추가하는 것**이다.

## V3 핵심 흐름

```text
D0 CONFIRMED
  -> 다음 거래일 시가 Stage 1 20%
  -> 매일 종가 재평가
  -> 강한 재상승 확인 시 다음 거래일 시가 Stage 2 30%
  -> 이후 새로운 강한 재상승이 다시 확인되면 다음 거래일 시가 Stage 3 50%
```

이전 V2에서 성과가 좋지 않았던 다음 로직은 제거했다.

- `CHASE_RISK -> WAIT_PULLBACK`
- 10거래일 후 `EXPIRED`
- Stage 1 대비 -2.5% 하락 시 Stage 2 물타기
- 단순 일간 급락만으로 후보를 폐기하는 `DAILY_CRASH`
- 단순 갭하락만으로 후보를 폐기하는 `GAP_DOWN_FAILED_RECOVERY`

## 분할매수

### Stage 1: 20%

Analyzer에서 `CONFIRMED`가 나오면 **다음 거래일 시가**에 20% 진입한다.

별도의 CHASE_RISK 대기나 READY_BUY 대기 없이 작은 비중으로 먼저 시작한다.

### Stage 2: 30%

아래 조건이 종가 기준으로 모두 확인되면 다음 거래일 시가에 30%를 추가한다.

- Daily Score >= 75
- 양봉
- 종가가 전일 고가 돌파
- 종가가 MA5 위
- 구조 훼손 / 대량 매도 신호 없음

즉, **가격이 내려왔기 때문에 추가하는 방식이 아니라 다시 강해졌기 때문에 추가한다.**

### Stage 3: 50%

Stage 2 체결 이후 별도의 새로운 재상승 확인이 다시 발생하면 다음 거래일 시가에 50%를 추가한다.

조건은 Stage 2와 동일하게 다음을 요구한다.

- Daily Score >= 75
- 새로운 양봉
- 새로운 전일 고가 돌파
- MA5 위
- 구조 훼손 없음

Stage 2와 Stage 3는 같은 확인 신호에서 동시에 체결하지 않는다.

## Daily Score 100점

- 가격 구조: 25
- 추세 / 이동평균: 20
- 캔들: 15
- 거래량: 15
- Heat 슬롯: 15
- 변동성 / 리스크: 10

V3에서는 이미 상승했다는 이유만으로 감점하지 않는다. 기존 Heat / Chase 슬롯은 100점 체계 호환을 위해 유지하지만 기본 15점으로 처리한다.

`signal_gain_pct`, `ma20_distance_pct`는 분석용 지표로 계속 출력한다.

## 추가매수 중단 조건

현재는 다음과 같은 구조 훼손 신호가 나오면 남은 추가매수를 중단한다.

- 종가가 구조적 손절선 아래
- 종가가 CONFIRMED 당일 저점 아래
- -4% 이상 하락하면서 거래량이 20일 평균 1.5배 이상인 대량 매도

이 조건은 기존 포지션을 즉시 시장가 청산하는 조건이 아니라 **추가매수를 막는 조건**이다. 실제 보유 포지션의 청산은 Hard Stop / Trailing Stop 로직이 담당한다.

## 매도

기존 백테스트에서 상대적으로 잘 작동한 매도 로직은 유지한다.

- Hard stop: 최근 10거래일 저점 아래 1%와 Stage 1 대비 -8% 중 더 타이트한 가격
- Trailing stop: 평균단가 대비 +10% 도달 후 최고 종가 대비 -7%
- Time exit: 실제 Stage 1 체결일부터 20거래일째 종가
- Slippage: 매수 / 매도 각 5bp

## 최신 CONFIRMED 종목 계획

```bat
PositionManager\run_position_manager.bat
```

입력:

```text
results\confirmed_candidates.csv
```

출력:

```text
PositionManager\results\position_plans.csv
```

주요 필드:

- `stage1_status`
- `stage1_reference_price`
- `scale_in_decision`
- `scale_in_reason`
- `add_confirmation`
- `daily_entry_score`
- `signal_gain_pct`
- `volume_ratio_20`
- `ma20_distance_pct`
- `stop_price`

신호 당일에는 다음 거래일 데이터가 없으므로 `STAGE1_NEXT_OPEN_PENDING` 상태가 정상이다.

## Range backtest

단독 실행:

```bat
PositionManager\run_range.bat 20260101~20260831
```

입력:

```text
results\range_YYYYMMDD_YYYYMMDD\confirmed_candidates.csv
```

출력:

```text
PositionManager\results\range_YYYYMMDD_YYYYMMDD\position_backtest.csv
PositionManager\results\range_YYYYMMDD_YYYYMMDD\daily_decisions.csv
PositionManager\results\range_YYYYMMDD_YYYYMMDD\position_backtest_summary.csv
```

`daily_decisions.csv`는 Stage 1 이후 각 거래일마다 추가매수가 가능한 상태였는지 기록한다.

`position_backtest.csv`에서는 Stage 1 / Stage 2 / Stage 3 실제 체결일과 가격, 실제 투자 비중, 손절 / 트레일링 / 기간청산 결과를 확인할 수 있다.

## Look-ahead 방지

- CONFIRMED는 D0 종가까지 확정된 정보로 본다.
- Stage 1은 D+1 시가에 체결한다.
- Stage 2 / Stage 3 조건은 당일 종가로 확인하고 다음 거래일 시가에 체결한다.
- 트레일링 스탑도 확정된 이전 종가 정보만 사용한다.
- 추가매수 승인과 당일 저가를 동시에 이용해 체결하는 로직은 사용하지 않는다.

## V3 설계 목적

```text
좋은 종목을 미리 너무 많이 걸러내지 않는다.
        +
처음에는 작게 진입한다.
        +
강도가 재확인될 때만 비중을 늘린다.
        +
구조가 깨지면 추가매수를 멈춘다.
        +
Hard Stop / Trailing으로 리스크를 관리한다.
```

즉 V3는 **선별을 더 강하게 하는 PositionManager가 아니라, Analyzer가 찾은 CONFIRMED 종목에 작게 들어가고 확인될수록 추가하는 PositionManager**다.
