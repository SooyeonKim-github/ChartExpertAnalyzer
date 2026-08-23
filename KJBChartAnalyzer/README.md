# Chart Confluence Stock Selector

강의록 1~3편의 내용을 **단일 공식이 아닌 신호 중첩(confluence) 방식**으로 구현한 주식 차트 분석 및 매수 후보 선별 프로젝트입니다.

## 1. 강의에서 직접 가져온 원칙

이 프로젝트는 다음 강의 프레임을 그대로 중심축으로 사용합니다.

1. **캔들**: 몸통, 위꼬리, 아래꼬리, 도지, 연속 양/음봉, 모닝스타/이브닝스타 유사 구조
2. **이동평균선**: 5/20/60/120, 정배열·역배열, 5-20 골든/데드크로스, 이평선 위/아래 위치
3. **이격**: 주가와 이평선의 과도한 괴리를 경계
4. **거래량**: 가격 움직임의 신뢰도 확인. 상승+거래량, 하락+거래량, 고점 대량거래·긴 위꼬리 경계
5. **지지·저항**: 반복 지지/저항, 돌파, 이탈, 저항→지지 역할전환
6. **추세**: 고점·저점의 방향과 이평선 배열을 우선 확인
7. **패턴**: W/더블바텀, 더블탑, 컵앤핸들, 헤드앤숄더/역헤드앤숄더
8. **분할매수·피라미딩**: 상승 추세에서 확인 신호가 늘 때 추가하되 뒤로 갈수록 수량 축소
9. **손절·트레일링스톱**: 손절선은 상승할 때 따라가지만 주가가 하락한다고 다시 낮추지 않음
10. **볼린저밴드**: 21일 중심선, 밴드 수축/팽창, 스퀴즈, 상·하단 밴드워킹
11. **교차검증**: 어느 한 신호도 절대 공식으로 쓰지 않음
12. **시장상태**: 추세장/하락장/횡보/변동성장을 구분. 피라미딩은 상승 추세장에서만 허용하는 방향

## 2. 강의 내용과 구현 규칙의 구분

강의는 많은 개념을 **정성적**으로 설명합니다. 예를 들어 '긴 꼬리', '거래량이 많이 터짐', '비슷한 두 바닥', '밴드가 좁아짐'에는 정확한 숫자 기준이 없습니다.

따라서 본 프로젝트에서 아래 값은 **강의의 뜻을 코드로 만들기 위해 추가한 구현 파라미터**이며, 강의가 직접 제시한 공식이 아닙니다.

- 긴 꼬리 = 전체 봉 길이의 45% 이상
- 거래량 확인 = 20일 평균 대비 1.5배 이상
- 강한 거래량 = 2배 이상
- 지지/저항 동일 구간 허용오차 = ±2%
- 볼린저 스퀴즈 = 최근 120일 밴드폭의 하위 20% 구간
- 기본 초기 손절 예시 = 8%, 최대 20%
- 트레일링스톱 예시 = 최근 고점 대비 12%
- 신호별 점수와 총점 컷

모든 값은 `config/default.yaml`에서 수정할 수 있습니다.

## 3. 분석 순서

```text
시장 상태
  ↓
이평선 정/역배열 + 고점/저점 구조
  ↓
현재 가격이 지지/저항 중 어디에 있는가
  ↓
캔들 힘(꼬리, 도지, 연속봉, 스타 패턴)
  ↓
거래량이 그 움직임을 확인하는가
  ↓
돌파/이탈/저항→지지 전환
  ↓
W, Cup & Handle, H&S 등 패턴
  ↓
볼린저 스퀴즈/밴드워킹
  ↓
신호 중첩 점수
  ↓
매수 후보 / 관찰 / 회피
  ↓
분할진입 + 구조적 손절 + 트레일링스톱
```

## 4. 핵심 파일

- `chartsel/analysis/analyzer.py`: 전체 분석 오케스트레이션
- `chartsel/analysis/scoring.py`: 신호 중첩 점수
- `chartsel/indicators/candlestick.py`: 캔들
- `chartsel/indicators/moving_average.py`: 이평선·정배열·골든/데드크로스
- `chartsel/reporting/plot.py`: 이평선·볼린저·지지저항 차트 출력
- `chartsel/indicators/volume.py`: 거래량 확인/고점 분배 힌트
- `chartsel/structure/support_resistance.py`: 지지·저항·역할전환
- `chartsel/structure/trend.py`: 고저점 구조와 추세
- `chartsel/patterns/*`: 쌍바닥/쌍봉/컵앤핸들/H&S
- `chartsel/indicators/bollinger.py`: 볼린저 스퀴즈/밴드워킹
- `chartsel/risk/risk_manager.py`: 분할매수/손절/트레일링
- `chartsel/selection/selector.py`: 여러 종목 랭킹
- `chartsel/backtest/engine.py`: 신호 발생 뒤 5/20/60일 사후수익률 검증

## 5. 설치

Windows PowerShell 또는 CMD:

```bash
cd chart_confluence_selector
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 6. 한 종목 분석

```bash
python app.py analyze --ticker 005930.KS --market ^KS11 --period 5y --out output/005930.json --chart output/005930.png
```

출력 예:

```text
[005930.KS]
점수=68.4/100  등급=B  판단=관심 매수 후보
trend       +18 | 정배열, 20일선 위, 저점 상승
location     +7 | 저항 돌파
volume       +6 | 상승+거래량 확인
...
```

## 7. 여러 종목에서 매수 후보 찾기

`tickers_example.txt`처럼 한 줄에 한 종목을 작성합니다.

```bash
python app.py screen --tickers tickers_example.txt --market ^KS11 --period 5y --out output/screen.csv
```

결과는 점수 순으로 정렬됩니다.

### 점수 해석

- A / 72 이상: **기술적 매수 후보**. 그래도 즉시 몰빵이 아니라 확인 후 분할진입
- B / 62 이상: 기술적 관심 매수 후보
- C / 52 이상: 관찰
- D / 40 이상: 보수적 관찰
- F / 40 미만: 매수 회피 또는 위험 구조 점검

점수는 확률 그 자체가 아닙니다. **강의 내용을 일관되게 비교하기 위한 랭킹 값**입니다.

## 8. 백테스트

강의의 중요한 주장인 '공식이 아니라 통계적으로 검증해야 한다'를 반영하여 이벤트 스터디를 포함했습니다.

```bash
python app.py backtest --ticker 005930.KS --period 10y --min-score 62 --out output/backtest_005930.csv
```

신호 점수가 62 이상이었던 날 이후:

- 5거래일 수익률
- 20거래일 수익률
- 60거래일 수익률
- 각 기간 승률

을 계산합니다.

이 결과를 이용해 `config/default.yaml`의 임계값을 검증해야 합니다.

## 9. 추천 고도화 방향

실전에서는 다음 단계가 중요합니다.

### A. 국내시장 데이터 연결
현재는 테스트하기 쉽게 `yfinance`와 CSV Provider가 있습니다. 기존 사내/개인 `market_data_service`가 있다면 `DataProvider` 인터페이스만 구현해 교체하면 됩니다.

### B. 지지·저항 정교화
현재는 Pivot 가격을 ±2%로 군집화합니다. 거래량 프로파일, 매물대, anchored VWAP 등을 별도 연구 지표로 추가할 수 있지만 이는 강의 원문에 없는 확장입니다.

### C. 패턴 후행성 검증
헤드앤숄더, 컵앤핸들은 사람이 보고 판단하는 요소가 많으므로 각 패턴 detector의 결과를 차트 위에 표시해 수동 검증하는 과정이 필요합니다.

### D. Walk-forward 검증
전체 기간에서 최적 임계값을 만든 뒤 같은 기간 성과를 보면 과최적화가 발생합니다. 과거 구간으로 설정하고 미래 구간에서 검증하는 walk-forward 방식이 필요합니다.

### E. 시장 레짐별 성과 분리
강의처럼 상승장·하락장·횡보·변동성장을 분리해 동일 신호가 어느 시장에서 잘 작동하는지 따로 확인하는 것이 좋습니다.


## 최종 매수 종목과 기술적 후보의 구분

강의는 차트만으로 최종 투자 결정을 내리지 않고 기업·산업·매크로를 같이 보라고 반복합니다. 하지만 강의에는 PER, ROE, 성장률 같은 구체적 재무 선별식이 없습니다. 그래서 이 프로젝트는 임의의 펀더멘털 공식을 만들지 않고 **사용자가 이미 투자대상으로 검토한 Universe 안에서 기술적으로 우선순위가 높은 종목을 고르는 역할**을 합니다.

즉 권장 파이프라인은:

```text
기업/산업/재무 기준으로 Universe 생성
        ↓
이 프로젝트로 차트 상태 분석
        ↓
기술적 후보 랭킹
        ↓
최종 투자 판단 + 포지션/손절 계획
```

`LECTURE_MAPPING.md`에서 강의 개념별 구현 위치를 확인할 수 있습니다.

## 10. 중요한 설계 원칙

이 프로젝트는 의도적으로 아래와 같은 코드를 만들지 않았습니다.

```python
if golden_cross:
    BUY()
```

대신:

```text
정배열인가?
+ 20일선 위인가?
+ 저점이 높아지는가?
+ 지지/저항 역할전환이 있는가?
+ 거래량이 돌파를 확인하는가?
+ 캔들이 반전을 지지하는가?
+ 패턴이 같은 방향인가?
+ 볼린저가 추세와 일치하는가?
+ 시장 자체가 추세장인가?
```

를 종합합니다.

이것이 강의에서 가장 반복적으로 강조한 **'여러 근거를 같이 보고 교차검증한다'**를 코드로 옮긴 핵심입니다.

---

> 주의: 이 프로젝트의 출력은 투자자문이나 수익 보장이 아니라 강의 내용을 재현하고 백테스트하기 위한 분석 도구입니다. 반드시 충분한 과거 검증과 별도 리스크 관리가 필요합니다.

## 11. 일봉/주봉 교차검증과 이격도

강의에서 같은 패턴도 일봉·주봉에 따라 다르게 보일 수 있다고 한 부분을 반영해, 데이터가 충분하면 일봉과 주봉의 이동평균 배열을 같이 평가합니다. 또한 20일선/120일선과의 이격이 설정값보다 지나치게 크면 강한 상승 중이라도 되돌림 경고를 추가합니다. 이격 임계값은 강의가 숫자로 제시하지 않았으므로 `config/default.yaml`의 구현 파라미터입니다.


## 12. 고도화 v2: 좋은 종목과 좋은 매수 타이밍 분리

기존 `신호 중첩 점수` 하나만으로는 **차트가 좋은 종목**과 **지금 신규 진입하기 좋은 종목**을 구분하기 어려웠습니다. v2에서는 아래 5개 점수를 동시에 출력합니다.

- `Selection Score`: 실제 종목 랭킹용 최종 비교점수. Technical 55% + Timing 45%에서 고위험 패널티 반영
- `Technical Score`: 중기 차트 품질. 일봉/주봉 정배열, 이동평균 기울기, 고점·저점 구조, 지지/저항 역할전환, 패턴 등
- `Timing Score`: 지금 이 가격의 신규 진입 적합도. MA20 이격, 지지선 근접, 눌림목, 저항 돌파, 당일 캔들·거래량, 시장상태 등
- `Risk Score`: 높을수록 위험. 역배열, 지지 붕괴, 고점 분배, 과도 이격, 하단 밴드워킹, 단기 급등 등을 반영
- `Confluence Score`: 기존 강의 7개 신호군을 중첩한 원형 점수. 강의 논리를 추적하기 위해 그대로 유지

따라서 다음처럼 서로 다른 결론이 가능합니다.

```text
Technical 88 / Timing 54 / Risk 38
→ 좋은 종목 · 눌림목 대기

Technical 76 / Timing 84 / Risk 27
→ 분할진입 우수

Technical 48 / Timing 78 / Risk 45
→ 단기 반전 후보 · 추세 확인 필요
```

### 매수 판단 상태

- `분할진입 우수`: 종목 상태와 현재 타이밍이 모두 양호
- `좋은 종목 · 눌림목 대기`: 중기 구조는 좋지만 단기 이격/급등으로 추격 위험
- `좋은 종목 · 저항 돌파 확인 대기`: 종목 상태는 좋지만 바로 위 저항이 가까움
- `좋은 종목 · 관심 진입`: 중기 구조가 좋고 타이밍도 무난
- `구조 개선 중 · 소액 정찰 가능`: 추세는 완전히 강하지 않지만 진입 신호가 먼저 개선
- `관심 종목 · 타이밍 확인 대기`: 종목은 관찰 가치가 있으나 신규 진입 근거 부족
- `매수 회피 · 구조 회복 확인`: 하락 구조 또는 위험신호 우세

## 13. 고도화된 결과화면

한 종목 분석 시 JSON/PNG뿐 아니라 HTML 대시보드를 만들 수 있습니다.

```bash
python app.py analyze --ticker 005930.KS --market ^KS11 --period 5y \
  --out output/005930.json \
  --chart output/005930.png \
  --report output/005930.html
```

HTML 상세화면에는 다음이 표시됩니다.

- Selection / Technical / Timing / Risk / Confluence 점수 카드
- 최종 판단: 지금 진입 / 눌림목 대기 / 저항 돌파 대기 / 회피
- 종목 기술적 상태 세부 점수
- 현재 매수 타이밍 세부 점수
- 핵심 강점 / 위험·대기 사유
- 지지선 / 저항선 / 초기 손절 / 트레일링 스톱
- 30% → 20% → 15% → 10% → 10% 피라미딩 단계와 현재 충족 여부
- 강의 신호 7개 범주의 원래 Confluence 상세점수
- 차트 이미지

`--report`만 지정하고 `--chart`를 생략하면 HTML 옆에 `_chart.png`를 자동 생성합니다.

### 여러 종목 랭킹 HTML

```bash
python app.py screen --tickers tickers_example.txt --market ^KS11 --period 5y \
  --out output/screen.csv \
  --report output/screen.html
```

랭킹 화면은 Selection → Timing → Technical → 낮은 Risk 순으로 정렬하며, 종목명/판단 검색 기능도 제공합니다.

## 14. v2 백테스트

이제 최종 Selection 점수뿐 아니라 Technical / Timing / Risk 조건을 별도로 걸어 검증할 수 있습니다.

```bash
python app.py backtest --ticker 005930.KS --period 10y \
  --min-score 68 \
  --min-technical 72 \
  --min-timing 70 \
  --max-risk 55 \
  --out output/backtest_005930.csv
```

이를 통해 예를 들어 `Technical >= 75`인 좋은 종목 전체와, 그중 `Timing >= 75 & Risk <= 50`인 실제 진입 후보의 이후 5/20/60일 성과를 따로 비교할 수 있습니다.

## 14. 사용자 제공 KOSPI_Info / pykrx 마켓데이터 연동

v3에서는 기존 v2 분석/점수/HTML 구조를 유지하고, 사용자가 제공한 `KOSPI_Info.xlsx`, `TickerUniverseService`, `PykrxDataProvider` 방식을 마켓데이터 계층에 추가했습니다.

### 데이터 역할 분리

- `KOSPI_Info.xlsx`: 분석 대상 Universe 생성에만 사용
- `시가총액`: TOP N 정렬 및 결과화면 표시
- `거래대금/거래량`: Universe 정렬 옵션으로만 사용 가능
- `pykrx`: 종목 일봉 OHLCV와 KOSPI/KOSDAQ 지수 일봉 조회
- 차트 Selection/Technical/Timing/Risk 점수에는 Excel의 재무/수급값을 직접 넣지 않음

### 시가총액 TOP100 한 번에 실행

```bash
python app.py screen-top100 --provider pykrx --info-excel KOSPI_Info.xlsx --top-n 100 --sort-by market_cap --period 5y --out output/top100_screen.csv --universe-out output/top100_universe.csv --report output/top100_screen.html
```

Windows에서는 `run_top100.bat`을 더블클릭하면 같은 명령이 실행됩니다.

생성 파일:

```text
output/top100_universe.csv  # Excel에서 뽑힌 원래 시총 TOP100
output/top100_screen.csv    # TOP100 차트 분석 후 Selection 순 재정렬
output/top100_screen.html   # 브라우저용 결과화면
```

### KOSPI / KOSDAQ 시장 교차검증

`TickerUniverseService`가 Excel의 `시장` 컬럼을 읽습니다. `screen-top100`은 KOSPI 종목에는 `^KS11`, KOSDAQ 종목에는 `^KQ11`을 벤치마크로 연결하고, 각 지수 데이터는 한 번만 조회해 캐시한 뒤 같은 시장 종목에 재사용합니다.

### 단일 종목을 pykrx로 분석

```bash
python app.py analyze --provider pykrx --ticker 005930 --market ^KS11 --period 5y --out output/005930.json --chart output/005930.png --report output/005930.html
```

`005930.KS`처럼 입력해도 PykrxProvider가 국내 6자리 종목코드로 정규화합니다.

### 다른 Universe 기준

거래대금 TOP100:

```bash
python app.py screen-top100 --provider pykrx --top-n 100 --sort-by trading_value --out output/top100_value.csv --report output/top100_value.html
```

거래량 TOP100:

```bash
python app.py screen-top100 --provider pykrx --top-n 100 --sort-by volume --out output/top100_volume.csv --report output/top100_volume.html
```

### 캐시

pykrx 조회 결과는 기본적으로 프로젝트의 `cache/` 폴더에 CSV로 저장하고 같은 종목/날짜 범위를 다시 요청할 때 재사용합니다. 메모리 캐시도 동시에 사용합니다.

캐시를 사용하지 않으려면:

```bash
python app.py screen-top100 --provider pykrx --no-cache
```

과거 특정 기준일로 재현하려면:

```bash
python app.py screen-top100 --provider pykrx --end-date 2026-08-21 --period 5y
```

## 14. 사용자 제공 KOSPI_Info / pykrx 마켓데이터 연동

v3에서는 기존 v2 분석/점수/HTML 구조를 유지하고, 사용자가 제공한 `KOSPI_Info.xlsx`, `TickerUniverseService`, `PykrxDataProvider` 방식을 마켓데이터 계층에 추가했습니다.

### 데이터 역할 분리

- `KOSPI_Info.xlsx`: 분석 대상 Universe 생성에만 사용
- `시가총액`: TOP N 정렬 및 결과화면 표시
- `거래대금/거래량`: Universe 정렬 옵션으로만 사용 가능
- `pykrx`: 종목 일봉 OHLCV와 KOSPI/KOSDAQ 지수 일봉 조회
- 차트 Selection/Technical/Timing/Risk 점수에는 Excel의 재무/수급값을 직접 넣지 않음

### 시가총액 TOP100 한 번에 실행

```bash
python app.py screen-top100 --provider pykrx --info-excel KOSPI_Info.xlsx --top-n 100 --sort-by market_cap --period 5y --out output/top100_screen.csv --universe-out output/top100_universe.csv --report output/top100_screen.html
```

Windows에서는 `run_top100.bat`을 더블클릭하면 같은 명령이 실행됩니다.

생성 파일:

```text
output/top100_universe.csv  # Excel에서 뽑힌 원래 시총 TOP100
output/top100_screen.csv    # TOP100 차트 분석 후 Selection 순 재정렬
output/top100_screen.html   # 브라우저용 결과화면
```

### KOSPI / KOSDAQ 시장 교차검증

`TickerUniverseService`가 Excel의 `시장` 컬럼을 읽습니다. `screen-top100`은 KOSPI 종목에는 `^KS11`, KOSDAQ 종목에는 `^KQ11`을 벤치마크로 연결하고, 각 지수 데이터는 한 번만 조회해 캐시한 뒤 같은 시장 종목에 재사용합니다.

### 단일 종목을 pykrx로 분석

```bash
python app.py analyze --provider pykrx --ticker 005930 --market ^KS11 --period 5y --out output/005930.json --chart output/005930.png --report output/005930.html
```

`005930.KS`처럼 입력해도 PykrxProvider가 국내 6자리 종목코드로 정규화합니다.

### 다른 Universe 기준

거래대금 TOP100:

```bash
python app.py screen-top100 --provider pykrx --top-n 100 --sort-by trading_value --out output/top100_value.csv --report output/top100_value.html
```

거래량 TOP100:

```bash
python app.py screen-top100 --provider pykrx --top-n 100 --sort-by volume --out output/top100_volume.csv --report output/top100_volume.html
```

### 캐시

pykrx 조회 결과는 기본적으로 프로젝트의 `cache/` 폴더에 CSV로 저장하고 같은 종목/날짜 범위를 다시 요청할 때 재사용합니다. 메모리 캐시도 동시에 사용합니다.

캐시를 사용하지 않으려면:

```bash
python app.py screen-top100 --provider pykrx --no-cache
```

과거 특정 기준일로 재현하려면:

```bash
python app.py screen-top100 --provider pykrx --end-date 2026-08-21 --period 5y
```
