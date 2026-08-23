# Market Data Integration Mapping

기존 Chart Confluence Selector v2를 유지하면서 사용자 제공 마켓데이터 코드를 다음 위치에 통합했습니다.

| 사용자 제공 파일 | v3 반영 위치 | 역할 |
|---|---|---|
| `KOSPI_Info.xlsx` | 프로젝트 루트 `KOSPI_Info.xlsx` | 시총/거래대금/거래량 기준 Universe |
| `data_provider.py` | `chartsel/data/pykrx_provider.py` | pykrx OHLCV, 메모리+CSV 캐시 |
| `ticker_universe_service.py` | `chartsel/universe/ticker_universe_service.py` | ETF 제외, TOP N 정렬, TickerInfo |
| `excel_reader.py` | `chartsel/universe/excel_reader.py` | 종목코드/종목명 정규화, 숫자 컬럼 정리 |
| `date_utils.py` | `chartsel/utils/date_utils.py` | 날짜 범위 + CLI period 변환 |
| `logger.py` | `chartsel/utils/logger.py` | TOP100 진행 로그 |

## 추가된 실행 흐름

```text
KOSPI_Info.xlsx
   ↓
TickerUniverseService
   ↓
ETF/ETN 제외
   ↓
시가총액 내림차순 TOP100
   ↓
TickerInfo(ticker, name, market, market_cap...)
   ↓
PykrxDataProvider
   ├─ 종목 OHLCV
   ├─ KOSPI 지수 (^KS11 → 1001)
   └─ KOSDAQ 지수 (^KQ11 → 2001)
   ↓
ChartAnalyzer
   ↓
Selection / Technical / Timing / Risk / Confluence
   ↓
Selection 순 재정렬
   ↓
CSV + HTML 결과
```

## 실행 명령

```bash
python app.py screen-top100 --provider pykrx --info-excel KOSPI_Info.xlsx --top-n 100 --sort-by market_cap --period 5y --out output/top100_screen.csv --universe-out output/top100_universe.csv --report output/top100_screen.html
```

또는 Windows에서 `run_top100.bat` 더블클릭.

## 중요

`KOSPI_Info.xlsx`의 시가총액/거래대금/거래량은 Universe 선별용입니다. 강의 기반 차트 점수에 직접 더하지 않습니다. 따라서 시총 TOP100 중 **차트 상태와 현재 진입 타이밍이 좋은 종목을 다시 찾는 구조**입니다.
