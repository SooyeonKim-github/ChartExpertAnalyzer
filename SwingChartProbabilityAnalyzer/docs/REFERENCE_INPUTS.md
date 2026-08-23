# 참고한 사용자 제공 코드

- `data_provider(2).py`: pykrx 수정주가 OHLCV 조회, 메모리 캐시, CSV 캐시 구조를 반영.
- `ticker_universe_service.py`: `KOSPI_Info.xlsx`를 고정 유니버스로 사용하는 방식을 반영.
- `excel_reader.py`: 종목코드/종목명 컬럼 자동 탐색과 6자리 코드 정규화 방식을 반영.
- `excel_writer.py`: 결과 Excel의 헤더/상태별 시각 구분 방식을 반영.
- `logger.py`, `date_utils.py`: 프로젝트 실행 로그와 히스토리 날짜 계산 구조를 반영.

신호 계산에는 위 Excel의 시가총액/거래대금/외국인비율/재무정보 등을 사용하지 않는다.
