# PullbackAnalyzer

독립적인 눌림목(Pullback) Analyzer V1.

## 핵심 원칙

눌림목은 "많이 빠진 종목"이 아니라 **선행 상승의 강함이 유지되는 조정**이다.  
따라서 `선행 상승 → 추세 유지 → 눌림 품질 → 거래량 감소 → 지지 중첩 → 재상승 확인 → 시장/RS/리스크` 순으로 평가한다.

## 100점 Score

| Component | Max |
|---|---:|
| Impulse | 15 |
| Trend | 15 |
| Pullback | 20 |
| Volume | 15 |
| Support | 15 |
| Confirmation | 10 |
| Market_Risk | 10 |
| Total | 100 |

`Score`는 눌림 자체의 품질이고 `Timing_Score`는 오늘의 진입 준비도를 뜻한다.

## 판정

- `CONFIRMED`: Score >= 70, Timing >= 60, 핵심 점수 하한 충족, 실제 confirmation trigger 존재, Hard Reject 없음
- `WATCH`: Score >= 50이며 Hard Reject 없음. 좋은 눌림이지만 반전/재돌파가 아직 부족한 상태 포함
- `REJECT`: Score < 50 또는 구조 붕괴/고거래량 breakdown/MA60 결정적 이탈/허리 붕괴 등 Hard Reject

## 시장 데이터

- 개별 종목: `pykrx`
- KOSPI/KOSDAQ 지수: 네이버 금융 index day
- 지수 OHLC는 시장 레짐/상대강도 계산에만 사용
- `KOSPI_Info.xlsx` 또는 공용 liquidity universe는 Universe 선별용이며 시가총액 자체를 Score에 더하지 않음

## 아직 점수화하지 않는 항목

강의에서 중요한 `재료 연속성`, `주도 섹터`, `악재 여부`는 현재 OHLCV/지수 데이터만으로 신뢰성 있게 만들 수 없으므로 V1 점수에서 제외한다. 결과에는 `Catalyst_Available=False`, `Sector_Context_Available=False`, `Adverse_News_Flag=UNKNOWN`을 남겨 후속 연동이 가능하게 한다.

## 실행

```bat
run_screen.bat
```

또는:

```bash
python main.py scan --info-excel KOSPI_Info.xlsx --top-n 100 --sort-by trading_value
python main.py explain --ticker 005930 --date 2026-09-01
```

기간 백테스트:

```bash
python main_range.py --date-range 20260101~20260831 --top-n 100 --sort-by trading_value --forward-bars 60
```

공용 point-in-time membership가 있으면 `--membership-csv`를 지정한다.

## 출력

당일:

- `results/YYYYMMDD/scan_results.csv`
- `results/YYYYMMDD/candidates.csv`
- `results/YYYYMMDD/pullback_candidates.xlsx`

기간:

- `range_all_results.csv`
- `range_candidates.csv`
- `events.csv`
- `performance_by_status.csv`
- `performance_by_pullback_type.csv`
- `pullback_range_backtest.xlsx`
