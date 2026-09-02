# PositionManager

`CONFIRMED` 신호 이후의 실제 진입 시점, 분할매수, 손절, 트레일링, 기간청산을 Analyzer와 독립적으로 관리한다.

핵심 원칙은 **오늘 종가까지 확정된 정보로 판단하고 실제 주문은 다음 거래일부터 실행**하는 것이다.

## Dynamic Daily Decision V2

`CONFIRMED = 즉시 매수`로 취급하지 않는다.

```text
D0 CONFIRMED
  -> D+1 종가 평가
  -> READY_BUY / WAIT_PULLBACK / WAIT_REBOUND / CANCEL
  -> READY_BUY일 때만 다음 거래일 시가 Stage 1
  -> 이후에도 매일 종가를 다시 평가하여 추가매수 허용 여부 결정
```

### Daily Score 100점

- 가격 구조: 25
  - D0 저점/구조적 손절선 유지
  - MA20 유지
  - 최근 저점 구조 유지
- 추세/MA: 20
  - Close > MA5
  - MA5 > MA10
  - MA10 > MA20
  - MA20 기울기
- 캔들: 15
  - 양봉
  - 종가가 당일 고가권
  - 전일 고가 돌파
- 거래량: 15
  - 상승+거래량 증가 우대
  - 눌림+거래량 감소 우대
  - 하락+거래량 폭증 감점
- 과열/추격 위험: 15
  - 신호가 대비 급등
  - MA20 이격 과다
- 변동성/리스크: 10
  - 최근 평균 일중 변동폭 대비 현재 변동폭

### Entry Decision

기본값은 `config.py`에서 조정한다.

- 80점 이상: `READY_BUY` -> 다음 거래일 시가 1차 매수
- 65~79점: `WAIT_REBOUND`
- 50~64점: 상황에 따라 `WAIT_REBOUND` 또는 `WAIT_PULLBACK`
- 50점 미만: `CANCEL`
- 최대 10거래일까지 관찰하고 미진입 시 `EXPIRED`
- 과열 상태는 점수가 높더라도 `WAIT_PULLBACK`

### Hard Cancel

첫 매수 전 다음 상황이면 점수와 관계없이 후보를 폐기한다.

- 종가가 구조적 손절선 아래
- 종가가 CONFIRMED 당일 저점 아래
- 일간 -5% 이상 급락
- -4% 이상 하락 + 거래량 20일 평균 1.5배 이상
- -5% 이상 갭하락 후 저가권 마감

## 분할매수

- Stage 1: Daily Decision이 `READY_BUY`가 된 **다음 거래일 시가**에 20%
- Stage 2: 전일 Daily Score 65점 이상 + Stage 1 체결가 대비 -2.5% 지정가에 30%
- Stage 3: 전일 Daily Score 75점 이상 + `양봉 + 종가가 전일 고가 상향 돌파 + 종가가 MA5 위` 확인 후 다음 거래일 시가에 50%
- 매수 후 Hard Cancel 성격의 가격 훼손이 나오면 남은 추가매수는 중단한다.

## 매도

- Hard stop: 최근 10거래일 저점 아래 1%와 Stage 1 대비 -8% 중 더 타이트한 가격
- Trailing stop: 평균단가 대비 +10% 도달 후 최고 종가 대비 -7%
- Time exit: 실제 Stage 1 체결일부터 20거래일째 종가
- Slippage: 매수/매도 각 5bp

## 최신 CONFIRMED 종목 계획

```bat
PositionManager\run_position_manager.bat
```

입력:

`results\confirmed_candidates.csv`

출력:

`PositionManager\results\position_plans.csv`

주요 필드:

- `daily_entry_decision`
- `daily_entry_score`
- `daily_entry_reason`
- `evaluation_date`
- `signal_gain_pct`
- `volume_ratio_20`
- `ma20_distance_pct`
- `stage1_status`

신호 당일에는 아직 D+1 데이터가 없으므로 `WATCHING_D1` 상태가 정상이다.

## Range backtest

`run_combined_range.bat` 실행 시 최종 CONFIRMED 집계 후 Dynamic PositionManager 백테스트가 자동 실행된다.

단독 실행:

```bat
PositionManager\run_range.bat 20260101~20260831
```

입력:

`results\range_YYYYMMDD_YYYYMMDD\confirmed_candidates.csv`

출력:

- `PositionManager\results\range_YYYYMMDD_YYYYMMDD\position_backtest.csv`
- `PositionManager\results\range_YYYYMMDD_YYYYMMDD\daily_decisions.csv`
- `PositionManager\results\range_YYYYMMDD_YYYYMMDD\position_backtest_summary.csv`

`daily_decisions.csv`는 각 CONFIRMED 신호에 대해 D+1, D+2, ... 매일 어떤 점수와 사유로 BUY/WAIT/CANCEL을 판단했는지 기록한다.

`strategy_return_on_planned_capital_pct`는 실제 체결 비중을 반영한 전체 계획자금 기준 수익률이다.
`position_return_pct`는 실제 투입된 금액만 기준으로 한 포지션 수익률이다.
`baseline_d20_pct`는 기존 Analyzer의 단순 D+20 수익률이다.
`alpha_vs_baseline_d20_pct`는 Dynamic PositionManager 결과와 기존 D+20 결과의 차이다.

매수를 취소하거나 신호가 만료된 경우 전략 수익률은 현금 보유 기준 0%로 두고, 해당 종목의 `baseline_d20_pct`도 계속 보존한다. 따라서 **취소한 종목이 실제로 이후 하락했는지, 혹은 좋은 수익 기회를 놓쳤는지** 검증할 수 있다.

## Look-ahead 방지

- D+1 종가 판단은 D+2 시가부터 반영한다.
- 모든 Daily Score는 해당 평가일 종가까지의 데이터만 사용한다.
- Stage 2의 당일 체결 허용 여부는 전일 종가 점수로 결정한다.
- Stage 3 조건은 종가로 확인한 뒤 다음 거래일 시가에 체결한다.
- 트레일링 스탑도 전일까지 확정된 trailing level을 다음 봉부터 적용한다.
- Stage 2와 stop이 같은 봉에 동시에 닿는 경우 stop을 우선한다.
