# MarketData

`ChartExpertAnalyzer`의 한국시장 공통 데이터 계층입니다. Analyzer 내부에서 `pykrx`, 네이버 금융, `yfinance`를 직접 호출하지 않고 이 패키지를 통해 접근하는 것을 원칙으로 합니다.

## 공통 책임

- 개별 종목 OHLCV: `MarketDataService.get_ohlcv()`
- KOSPI/KOSDAQ 지수: `MarketDataService.get_market_index()` (네이버 지수)
- 최근 거래일: `MarketDataService.resolve_trading_date()`
- 시장 일간 수익률: `MarketDataService.get_market_return()`
- KRX 전체시장 snapshot: `MarketDataService.get_market_snapshot()`
- Excel 종목 Universe: `ExcelUniverseService`
- 최근 N거래일 평균 거래대금 point-in-time TOP N: `build_liquidity_universe()`
- 공통 캐시: `cache/MarketData/`

## Provider 우선순위

종목 OHLCV는 `cache -> pykrx 종목별 기간 조회 -> yfinance fallback`, 시장지수는 `cache -> Naver index` 순서입니다. KRX 전체시장 snapshot이 실패하면 liquidity universe는 현재 Excel 후보군을 대상으로 종목별 OHLCV 방식으로 자동 전환합니다.

Analyzer의 패턴/점수/CONFIRMED-WATCH-REJECTED 로직은 이 패키지에 두지 않습니다. 이 폴더는 오직 시장 데이터와 Universe만 책임집니다.
