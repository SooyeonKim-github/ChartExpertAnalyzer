# 강의 내용 → 프로젝트 구현 매핑

이 문서는 강의에서 설명한 내용을 코드 어디에 반영했는지 추적하기 위한 체크리스트입니다.

| 강의 개념 | 구현 위치 | 구현 방식 |
|---|---|---|
| 캔들 OHLC | `indicators/candlestick.py` | 몸통/위꼬리/아래꼬리 비율 계산 |
| 긴 위꼬리/아래꼬리 | `candlestick.py`, `scoring.py` | 60일 가격 위치와 함께 해석 |
| 도지 | `candlestick.py` | 몸통 비율 기반 근사, 고점/저점 위치에 따라 방향 다르게 평가 |
| 연속 3양봉/3음봉 | `candlestick.py` | 최근 3봉 방향 및 종가 진행 확인 |
| 모닝스타/이브닝스타 | `candlestick.py` | 3봉 구조를 정량화한 근사 |
| 일봉/주봉 교차검증 | `analysis/analyzer.py`, `structure/trend.py` | 일봉을 주봉으로 재표본화 후 배열 비교 |
| 5/20/60/120 이평선 | `indicators/moving_average.py` | 단순이동평균 |
| 정배열/역배열 | `moving_average.py` | MA5>MA20>MA60>MA120 / 반대 |
| 골든/데드크로스 | `moving_average.py` | 5-20 교차 탐지 |
| 이격도 | `structure/trend.py` | 종가와 20/120일선 거리 측정, 과도 이격 경고 |
| 거래량 신뢰도 | `indicators/volume.py` | 20일 평균 대비 상대거래량 |
| 고점 대량거래+위꼬리 | `volume.py`, `scoring.py` | 분배 가능성 경고 |
| 지지/저항 | `structure/support_resistance.py` | Pivot 저고점 군집화 |
| 저항→지지 역할전환 | `support_resistance.py` | 돌파 후 재접근 확인 |
| 지지선 이탈 | `support_resistance.py` | 종가 기준 breakdown |
| 상승/하락 구조 | `structure/trend.py` | higher high/lower low 등 최근 Pivot 비교 |
| 박스권/비추세장 | `analysis/market_regime.py` | 이평 배열과 변동성으로 range 분류 |
| 쌍바닥/W | `patterns/double_patterns.py` | 유사한 두 저점과 중간 고점 |
| 쌍봉/Double Top | `patterns/double_patterns.py` | 유사한 두 고점과 중간 저점 |
| Cup & Handle | `patterns/cup_handle.py` | 큰 바닥, 전고점 회복, 높은 손잡이 저점 근사 |
| Head & Shoulders | `patterns/head_shoulders.py` | 3개 pivot 고점의 어깨-머리-어깨 구조 |
| 역 Head & Shoulders | `patterns/head_shoulders.py` | 3개 pivot 저점의 역구조 |
| 추세장 피라미딩 | `risk/risk_manager.py`, `analysis/analyzer.py` | 초기 비중 크게, 추가 비중 점차 감소. 시장 uptrend 조건 |
| 물타기 경고 | `README.md` | 하락할수록 무조건 추가하지 않음 |
| 손절 | `risk/risk_manager.py` | 설정 비율과 구조적 지지선 조합 |
| 트레일링스톱 | `risk/risk_manager.py` | 최고가 기준 일정 비율 아래. 하락 시 stop을 낮추지 않는 개념 |
| 볼린저 중심선 | `indicators/bollinger.py` | 21일선 기본값 |
| 밴드 수축/팽창 | `bollinger.py` | BB width |
| 스퀴즈 | `bollinger.py` | 최근 밴드폭 하위 분위수. 방향 점수는 0 |
| 상단 밴드워킹 | `bollinger.py`, `scoring.py` | 정배열 상승에서 상단 근접 지속 시 강세 |
| 하단 밴드워킹 | `bollinger.py`, `scoring.py` | 역배열 하락에서 하단 근접 지속 시 약세 |
| 여러 신호 교차검증 | `analysis/scoring.py` | 7개 범주의 confluence 합산 |
| 단일 공식 금지 | 전체 구조 | 단일 신호로 BUY를 발생시키지 않음 |
| 기업/산업/매크로 병행 | 입력 Universe 설계 | 강의에 숫자 기준이 없으므로 임의 재무공식은 구현하지 않음. `tickers`를 사전 선별된 Universe로 받음 |
| 과거통계 검증 | `backtest/engine.py` | 점수 발생 후 5/20/60일 사후수익률 이벤트 스터디 |

## 강의가 수치로 주지 않은 항목

아래 기준은 **강의 원문이 아닌 구현상 정량화**입니다.

- 긴 꼬리의 비율
- 거래량 1.5배/2배 기준
- 지지/저항 허용오차 2%
- 패턴의 유사도 허용범위
- 스퀴즈 percentile
- 이격도 경고 임계값
- 신호별 가중치
- A/B/C/D/F 컷
- 초기 손절 및 트레일링 비율

따라서 실전 사용 전에 반드시 백테스트/워크포워드 검증으로 조정해야 합니다.


## v2 의사결정 계층 추가

강의가 반복해서 강조한 "좋은 차트"와 "지금의 매수/매도 시점"을 코드에서 분리하기 위해 `chartsel/analysis/decision.py`를 추가했습니다.

- `Technical Score`: 정배열/역배열, 일봉·주봉 교차검증, 고점·저점 상승/하락, 지지·저항 역할전환, W·Cup·H&S, 밴드워킹처럼 비교적 느리게 변하는 구조
- `Timing Score`: 지지선까지 거리, 돌파 직후인지/눌림목인지, 골든·데드크로스, 도지·꼬리·모닝/이브닝스타, 상대거래량, MA20 이격, 볼린저 위치, 시장 레짐처럼 현재 진입 위치에 민감한 요소
- `Risk Score`: 강의의 고점 거래량+긴 위꼬리, 지지 붕괴, 역배열, 이격 과다, 하단 밴드워킹, 변동성장 경고를 별도 위험도로 집계
- `Entry Status`: 위 점수를 조합해 `분할진입 우수 / 눌림목 대기 / 저항 돌파 대기 / 관찰 / 회피`로 번역
- `contextual_entry_plan`: 강의의 피라미딩 예시를 실제 신호 충족 여부와 연결

스퀴즈 자체는 방향 점수를 주지 않는 기존 원칙을 유지하며, 상단 터치 역시 정배열 밴드워킹이면 과열 매도로 단순 처리하지 않습니다.
