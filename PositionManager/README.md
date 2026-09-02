# PositionManager

`CONFIRMED` 신호 이후의 분할매수/손절/트레일링/기간청산을 Analyzer와 독립적으로 관리한다.

## V1 기본 규칙

- Stage 1: CONFIRMED 다음 거래일 시가에 20%
- Stage 2: Stage 1 체결가 대비 -2.5% 지정가에 30%, 최초 10거래일 안에서만 유효
- Stage 3: Stage 2 이후 `양봉 + 종가가 전일 고가 상향 돌파 + 종가가 MA5 위` 확인 후 다음 거래일 시가에 50%
- Hard stop: 최근 10거래일 저점 아래 1%와 Stage 1 대비 -8% 중 더 타이트한 가격
- Trailing stop: 평균단가 대비 +10% 도달 후 최고 종가 대비 -7%
- Time exit: Stage 1 체결일부터 D+20 종가
- Slippage: 매수/매도 각 5bp

모든 파라미터는 `config.py`에서 변경할 수 있다.

## 최신 CONFIRMED 종목 계획

```bat
PositionManager\run_position_manager.bat
```

입력: `results\confirmed_candidates.csv`

출력: `PositionManager\results\position_plans.csv`

## Range backtest

`run_combined_range.bat` 실행 시 최종 CONFIRMED 집계 후 PositionManager 백테스트가 자동 실행된다.

단독 실행:

```bat
PositionManager\run_range.bat 20260101~20260831
```

입력: `results\range_YYYYMMDD_YYYYMMDD\confirmed_candidates.csv`

출력:
- `PositionManager\results\range_YYYYMMDD_YYYYMMDD\position_backtest.csv`
- `PositionManager\results\range_YYYYMMDD_YYYYMMDD\position_backtest_summary.csv`

`strategy_return_on_planned_capital_pct`는 실제 체결된 Stage 비중을 반영한 전체 계획자금 기준 수익률이다.
`position_return_pct`는 실제 투입된 금액만 기준으로 한 포지션 수익률이다.
`baseline_d20_pct`는 기존 Analyzer의 단순 D+20 수익률이며 비교용으로 보존한다.

## Look-ahead 처리

- Stage 1은 신호 다음 거래일 시가 체결
- Stage 3 조건은 종가로 확인한 뒤 다음 거래일 시가에 체결
- 트레일링 스탑도 전일까지 확정된 trailing level을 다음 봉부터 적용
- Stage 2와 stop이 같은 봉에 동시에 닿는 경우 보수적으로 stop을 우선한다
