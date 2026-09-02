# MaterialAnalyzer V1 - Material Collector

`MaterialAnalyzer`는 차트 Analyzer와 독립적으로 **주가를 움직일 수 있는 재료의 원천 데이터**를 수집하기 위한 모듈입니다.

V1의 첫 단계는 점수화가 아니라 수집입니다. 강의의 흐름인 `일정/뉴스 발견 -> 관련 테마/종목 정리 -> 과거 반응 확인 -> 실제 시장 반응 확인`을 구현하기 위해, 먼저 뉴스/정책/공시를 같은 포맷으로 누적합니다.

## V1 수집원

1. **Naver News Search API**
   - `data/news_queries.csv`의 검색어를 날짜순으로 조회
   - 뉴스 제목/요약/원문 링크/검색 카테고리 저장
   - `예정`, `공청회`, `간담회`, `정상회담`, `출시`, `상장` 등 미래 일정 힌트 표시
   - API 키가 없으면 해당 소스만 SKIP

2. **대한민국 정책브리핑 보도자료**
   - `https://www.korea.kr/briefing/pressReleaseList.do`
   - API 키 없이 최신 보도자료 링크 수집
   - 정부 정책/투자/산업지원 재료의 원천 데이터 용도

3. **OpenDART 공시검색 API**
   - 지정 날짜 기준 최근 N일 공시 수집
   - 종목코드, 기업코드, 접수번호 저장
   - API 키가 없으면 해당 소스만 SKIP

## 왜 Collector와 Analyzer를 분리하는가

뉴스 API나 수집 사이트가 바뀌더라도 재료 점수화 로직이 영향을 받지 않도록 하기 위함입니다.

```text
Naver News -----\
Policy Briefing ---> MaterialCollector ---> collected_materials.csv
OpenDART -------/                            |
                                             v
                                      Material Analyzer V2
                                      - novelty
                                      - continuity
                                      - beneficiary
                                      - historical reaction
                                      - market confirmation
```

## 설치

기존 가상환경을 사용한다면:

```bat
pip install -r MaterialAnalyzer\requirements.txt
```

## API 키 설정

### Naver News

Windows CMD:

```bat
set NAVER_CLIENT_ID=발급받은_CLIENT_ID
set NAVER_CLIENT_SECRET=발급받은_CLIENT_SECRET
```

필요하면 엔드포인트를 환경변수로 교체할 수 있습니다.

```bat
set NAVER_NEWS_API_URL=https://openapi.naver.com/v1/search/news.json
```

### OpenDART

```bat
set OPENDART_API_KEY=발급받은_API_KEY
```

API 키는 Git 저장소에 저장하지 않습니다.

## 실행

```bat
MaterialAnalyzer\run_collect.bat
```

또는 저장소 루트에서:

```bat
python -m MaterialAnalyzer.main
python -m MaterialAnalyzer.main --date 20260902
python -m MaterialAnalyzer.main --sources policy
python -m MaterialAnalyzer.main --query-limit 5
```

## 검색어 수정

`MaterialAnalyzer/data/news_queries.csv`

```csv
category,query,enabled
policy,정부 투자,1
event,공청회 예정,1
industry,우크라이나 재건,1
industry,양자컴퓨터,1
```

- `category`: 재료 대분류
- `query`: Naver News 검색어
- `enabled`: `1` 사용, `0` 미사용

검색어는 점수 규칙이 아닙니다. **수집 Recall을 높이기 위한 입력 목록**입니다.

## 출력

일별 스냅샷:

```text
MaterialAnalyzer/results/YYYYMMDD/collected_materials.csv
```

누적 원천 DB:

```text
MaterialAnalyzer/data/material_items.csv
```

주요 컬럼:

```text
dedup_key
collected_at
published_at
source_type
source
title
summary
url
query
category
ticker
corp_code
report_code
future_hint
```

같은 URL은 `dedup_key` 기준으로 누적 DB에 중복 저장하지 않습니다.

## V1에서 하지 않는 것

Collector 단계에서는 다음을 의도적으로 판단하지 않습니다.

- 좋은 재료인지 점수화
- 수혜 섹터/종목 LLM 추론
- 과거 동일 재료 수익률
- 당일 거래대금/등락률 확인
- CONFIRMED / WATCH / REJECT 분류
- 매수 타이밍 판단

이 기능들은 Collector가 안정적으로 데이터를 쌓은 뒤 V2 Analyzer 계층에서 추가합니다.
