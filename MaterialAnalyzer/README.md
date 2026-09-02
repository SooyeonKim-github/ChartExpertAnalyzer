# MaterialAnalyzer V1 - Material + Schedule Collector

`MaterialAnalyzer`는 차트 Analyzer와 독립적으로 **주가를 움직일 수 있는 재료의 원천 데이터와 예정 일정을 수집**하기 위한 모듈입니다.

강의의 흐름인 `일정/뉴스 발견 -> 관련 테마/종목 정리 -> 과거 반응 확인 -> 실제 시장 반응 확인`을 코드화하기 위해, V1은 점수화보다 수집과 일정 정리에 집중합니다.

## V1 수집원

1. **Naver News Search API**
   - `data/news_queries.csv`의 검색어를 날짜순으로 조회
   - 뉴스 제목/요약/원문 링크/검색 카테고리 저장
   - API 키가 없으면 해당 소스만 SKIP

2. **대한민국 정책브리핑 보도자료**
   - `https://www.korea.kr/briefing/pressReleaseList.do`
   - 정부 정책/투자/산업지원 재료의 원천 데이터 용도

3. **OpenDART 공시검색 API**
   - 지정 날짜 기준 최근 N일 공시 수집
   - 종목코드, 기업코드, 접수번호 저장
   - API 키가 없으면 해당 소스만 SKIP

4. **ScheduleCollector**
   - 위에서 수집한 뉴스/정책/공시 문장을 다시 검사
   - `예정`, `공청회`, `간담회`, `정상회담`, `발표`, `회의`, `방문`, `상장`, `출시`, `착공`, `시행` 등 일정성 키워드 확인
   - 동시에 `9월 5일`, `2026년 9월 5일`, `내일`, `모레`, `오는 금요일`, `오후 2시`, `14:30`처럼 실제 날짜/시간이 해석되는 경우만 일정 후보로 채택
   - 기본적으로 기준일부터 앞으로 21일 이내 일정만 저장
   - 날짜가 없는 단순 `추진 계획`, `산업 육성` 문구는 일정 후보에서 제외

## 구조

```text
Naver News -----\
Policy Briefing ---> MaterialCollector ---> collected_materials.csv
OpenDART -------/            |
                             v
                      ScheduleCollector
                             |
                             +--> schedule_candidates.csv
                             |
                             v
                   Material Analyzer V2
                   - novelty
                   - continuity
                   - beneficiary
                   - historical reaction
                   - market confirmation
```

`ScheduleCollector`는 재료 강도를 평가하지 않습니다. **앞으로 시장이 반응할 수 있는 날짜를 미리 정리하는 역할**만 담당합니다.

## 설치

```bat
pip install -r MaterialAnalyzer\requirements.txt
```

## API 키 설정

### Naver News

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

## 전체 실행

```bat
MaterialAnalyzer\run_collect.bat
```

기본 실행은 다음 단계를 모두 수행합니다.

```text
naver + policy + dart + schedule
```

또는 저장소 루트에서:

```bat
python -m MaterialAnalyzer.main
python -m MaterialAnalyzer.main --date 20260902
python -m MaterialAnalyzer.main --schedule-lookahead 14
python -m MaterialAnalyzer.main --query-limit 5
```

## 일정 수집만 실행

```bat
MaterialAnalyzer\run_schedule.bat
```

이 BAT는 빠르게 일정 후보만 확인할 수 있도록 다음 소스를 사용합니다.

```text
naver + policy + schedule
```

기본 미래 탐색 범위는 21일이며 실행 시 변경할 수 있습니다.

## 검색어 수정

`MaterialAnalyzer/data/news_queries.csv`

```csv
category,query,enabled
policy,정부 투자,1
event,발표 예정,1
event,공청회 예정,1
event,간담회 개최,1
event,정상회담,1
industry,우크라이나 재건,1
```

- `category`: 재료 대분류
- `query`: Naver News 검색어
- `enabled`: `1` 사용, `0` 미사용

검색어는 점수 규칙이 아니라 **수집 Recall을 높이기 위한 입력 목록**입니다.

## 출력

### 원천 재료 일별 스냅샷

```text
MaterialAnalyzer/results/YYYYMMDD/collected_materials.csv
```

### 일정 후보 일별 스냅샷

```text
MaterialAnalyzer/results/YYYYMMDD/schedule_candidates.csv
```

주요 일정 컬럼:

```text
event_date
event_time
schedule_kind
confidence
title
summary
source
url
date_evidence
```

예:

```text
2026-09-05,14:00,정책발표,0.95,...,9월 5일
2026-09-06,,정상회담,0.90,...,내일
```

### 누적 원천 DB

```text
MaterialAnalyzer/data/material_items.csv
```

### 누적 일정 DB

```text
MaterialAnalyzer/data/schedule_items.csv
```

각 DB는 `dedup_key` 기준으로 중복 누적을 방지합니다.

## V1에서 하지 않는 것

Collector 단계에서는 다음을 의도적으로 판단하지 않습니다.

- 좋은 재료인지 점수화
- 수혜 섹터/종목 LLM 추론
- 과거 동일 재료 수익률
- 당일 거래대금/등락률 확인
- CONFIRMED / WATCH / REJECT 분류
- 매수 타이밍 판단

이 기능들은 Collector가 데이터를 충분히 쌓은 뒤 Analyzer 계층에서 추가합니다.
