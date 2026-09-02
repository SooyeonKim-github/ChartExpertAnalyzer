# CloseBetAnalyzer V1

종가배팅 강의의 핵심 흐름 중 **기존 ChartExpertAnalyzer 코드로 검증 가능한 부분을 우선 재사용**한 독립 Analyzer입니다.

## V1 범위

V1은 매수 당일의 분봉/호가/프로그램 수급을 자동 분석하지 않습니다.

대신 두 단계를 분리합니다.

1. 이미 완료된 일봉 데이터로 종가배팅 후보를 고릅니다.
2. 후보마다 오늘 실제 주가를 보면서 사용할 수 있는 **가격 가이드**를 숫자로 출력합니다.

즉 `CloseBetAnalyzer`가 후보를 골라주고, 사용자는 장중 특히 14:30 이후 현재가를 `buy_day_guides.csv`의 가격선과 비교해 최종 매수 여부를 판단합니다.

## 기존 코드 재사용

다음 모듈을 새로 복제하지 않고 그대로 import합니다.

- `KJBChartAnalyzer/chartsel/data/pykrx_provider.py`
  - 국내 주식/ETF 일봉, KOSPI/KOSDAQ 지수, 캐시
- `KJBChartAnalyzer/chartsel/universe/ticker_universe_service.py`
  - 기존 Universe 로딩
- `KJBChartAnalyzer/chartsel/analysis/market_regime.py`
  - 시장 uptrend/range/volatile/downtrend
- `KJBChartAnalyzer/chartsel/analysis/relative_strength.py`
  - 종목의 지수 대비 상대강도
- `KJBChartAnalyzer/chartsel/sector/*`
  - 섹터 매핑, 섹터 거래대금 흐름, 섹터 상대강도/종합점수
- `KJBChartAnalyzer/chartsel/indicators/moving_average.py`
- `KJBChartAnalyzer/chartsel/indicators/volume.py`
- `KJBChartAnalyzer/chartsel/indicators/candlestick.py`
- `KJBChartAnalyzer/chartsel/structure/pivots.py`
- `KJBChartAnalyzer/chartsel/structure/trend.py`
- `KJBChartAnalyzer/chartsel/structure/support_resistance.py`

기존 Analyzer의 판정 결과를 섞지는 않습니다. KJB/Swing/MA와 별도의 독립 Analyzer입니다.

## V1 점수

현재 총점은 다음 Feature를 계층적으로 정리하기 위한 **초기 검증용 점수**입니다.

- 시장 상태 15%
- 섹터 강도 20%
- 종목 상대강도 20%
- 거래대금 Universe 순위 15%
- 일봉 구조 25%
- 거래량 품질 5%

임계값은 강의에서 제시된 고정 숫자가 아니라 코드화를 위한 초기값입니다. Range backtest 후 조정해야 합니다.

상태:

- `STRONG_CONFIRMED`
- `CONFIRMED`
- `WATCH`
- `REJECTED`

## 매수 당일 가이드

`buy_day_guides.csv`의 핵심 컬럼:

- `guide_reference_close`: 후보 분석 기준 종가
- `guide_preferred_low`: 오늘 가격이 이 정도 조정 범위 안이면 우선 관찰
- `guide_preferred_high`: 무리한 추격 없이 볼 수 있는 기본 상단
- `guide_hold_level`: 후보 논리가 유지되려면 가급적 지켜야 할 가격
- `guide_cancel_below`: 이 아래면 종가배팅 취소 우선
- `guide_chase_above`: 이 위면 추격매수 금지 우선
- `guide_buy_if`
- `guide_wait_if`
- `guide_skip_if`

V1은 이 조건을 자동 체결 신호로 사용하지 않습니다. **오늘 현재가가 어떻게 움직이는지 직접 보고 최종 판단하기 위한 가이드**입니다.

## 실행

```bat
CloseBetAnalyzer\run_screen.bat
```

또는:

```bash
python CloseBetAnalyzer/main.py --top-n 100 --sort-by trading_value
```

루트의 `prepare_liquidity_universe.bat`를 먼저 실행해서 `LIQUIDITY_UNIVERSE_XLSX` 환경변수가 연결되어 있으면 그 Universe를 그대로 사용할 수 있고, 없으면 KJB의 `KOSPI_Info.xlsx`를 사용합니다.

## 출력

```text
CloseBetAnalyzer/results/YYYYMMDD/
├─ scan_results.csv
├─ candidates.csv
├─ buy_day_guides.csv
└─ errors.csv
```

## 아직 구현하지 않은 부분

강의에는 중요하지만 기존 repository의 안정적인 production 데이터 모듈이 없어 V1에 억지로 넣지 않은 항목입니다.

- 종목별 외국인/기관 순매수
- 프로그램 매매
- 뉴스/재료 지속성
- 매수 당일 1분/3분봉 자동 판정
- 시간외 단일가
- 유동주식수 회전율
- 매수 논리(Thesis) 훼손 자동 감지

이 항목들은 별도 Provider가 확보된 뒤 V2+에서 추가하는 것이 맞습니다.
