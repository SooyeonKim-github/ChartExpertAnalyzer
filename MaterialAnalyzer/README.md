# MaterialAnalyzer V1 - Material + Schedule Analysis

`MaterialAnalyzer`는 차트 Analyzer와 독립적으로 **주가를 움직일 수 있는 재료의 원천 데이터와 예정 일정을 수집하고, 일정 중요도와 관련 테마/종목을 정리**하는 모듈입니다.

강의 흐름을 다음처럼 단계적으로 코드화합니다.

```text
일정/뉴스 발견
    -> 예정 일정 추출
    -> 일정 중요도 평가
    -> 관련 테마 정리
    -> 관련 종목 정리
    -> 과거 실제 주가 반응 확인 (다음 단계)
    -> 당일 시장 반응 확인 (다음 단계)
```

## 1. 수집 계층

### Naver News Search API
- `data/news_queries.csv` 검색어를 날짜순으로 조회
- 뉴스 제목/요약/링크/검색 카테고리 저장
- API 키가 없으면 해당 소스만 SKIP

### 대한민국 정책브리핑
- 정부 정책/투자/산업지원 보도자료 수집

### OpenDART
- 지정 날짜 기준 최근 N일 공시 수집
- 종목코드/기업코드/접수번호 저장

### ScheduleCollector
- 수집 문장에서 미래 일정성 키워드와 실제 날짜 표현을 동시에 확인
- `9월 5일`, `2026년 9월 5일`, `22일`, `내일`, `모레`, `오는 금요일`, `오후 2시`, `14:30` 등을 해석
- 기본적으로 기준일부터 향후 21일 일정만 저장
- 날짜가 없는 단순 계획/추진 문구는 제외

출력:

```text
MaterialAnalyzer/results/YYYYMMDD/collected_materials.csv
MaterialAnalyzer/results/YYYYMMDD/schedule_candidates.csv
MaterialAnalyzer/data/material_items.csv
MaterialAnalyzer/data/schedule_items.csv
```

## 2. ScheduleImportanceAnalyzer

`schedule_candidates.csv`의 각 일정을 100점으로 평가합니다.

| 항목 | 최대점수 | V1 의미 |
|---|---:|---|
| Authority | 15 | 대통령/정부/부처/공공기관 등 발표 주체 |
| Novelty | 20 | 누적 material history에서 유사 내용 반복 정도 |
| Money Scale | 15 | 기사에 명시된 투자/지원 금액 |
| Policy Strength | 15 | 대책/로드맵/법/예산/시행 등 정책 강도 |
| Theme Clarity | 15 | theme_keywords.csv 직접 매칭 명확성 |
| Event Certainty | 20 | ScheduleCollector 날짜 추출 confidence |

```text
85 이상 : A_PRIORITY
70~84   : WATCH
55~69   : LOW_PRIORITY
55 미만 : IGNORE
```

### Novelty 주의

누적 과거 데이터가 부족하면 `novelty_score=10`의 중립값과 함께

```text
novelty_status=INSUFFICIENT_HISTORY
```

를 남깁니다. 과거 데이터가 없다는 이유로 새 재료라고 단정하지 않습니다.

**과거 동일 재료의 실제 주가 수익률은 아직 점수에 포함하지 않습니다.** 이것은 다음 `HistoricalReactionAnalyzer`에서 별도로 계산합니다.

## 3. ThemeMapper

테마 사전:

```text
MaterialAnalyzer/data/theme_keywords.csv
```

예:

```csv
 theme,keywords,enabled
 자율주행,자율주행|ADAS|로보택시|무인차,1
 양자기술,양자기술|양자컴퓨터|양자암호|양자통신,1
 원전,원전|원자력|SMR|원전 수출,1
```

V1은 **키워드에 실제 근거가 있는 테마만 반환**합니다. LLM 추론으로 없는 테마를 만들어내지 않습니다.

## 4. ThemeStockMapper

테마-종목 관계:

```text
MaterialAnalyzer/data/theme_stocks.csv
```

주요 컬럼:

```text
theme
ticker
name
relevance
relation_type
reason
enabled
```

`relevance`는 0~1이며 `stock_theme_score = relevance * 100`으로 출력됩니다.

현재 CSV의 구체적인 종목 관계는 **초기 수동 seed 데이터**입니다. 강의록에서 직접 제시한 종목 목록이라는 의미가 아니며, 이후 뉴스 언급 빈도와 실제 주가 반응으로 검증/교체하는 것을 전제로 합니다.

## 5. 일정 분석 실행

먼저 일정 수집:

```bat
MaterialAnalyzer\run_collect.bat
```

그 다음 중요도 + 테마 + 종목 연결:

```bat
MaterialAnalyzer\run_analyze_schedule.bat
```

또는 저장소 루트에서:

```bat
python -m MaterialAnalyzer.analyze_schedule
python -m MaterialAnalyzer.analyze_schedule --date 20260902
```

입력:

```text
MaterialAnalyzer/results/YYYYMMDD/schedule_candidates.csv
```

출력:

```text
MaterialAnalyzer/results/YYYYMMDD/schedule_analysis.csv
```

주요 출력 컬럼:

```text
scan_date
event_date
event_time
schedule_kind
title
schedule_score
priority
authority_score
novelty_score
money_score
policy_score
theme_clarity_score
event_certainty_score
novelty_status
similar_history_count
money_amount_krw
theme
theme_confidence
theme_match_type
matched_keywords
ticker
name
stock_theme_score
relation_type
reason
source
url
```

하나의 일정에 여러 테마/종목이 연결되면 여러 행으로 확장합니다. 테마 또는 종목이 매핑되지 않아도 일정 자체는 삭제하지 않고 빈 값으로 보존합니다.

## 설치 및 API 키

```bat
pip install -r MaterialAnalyzer\requirements.txt
```

Naver:

```bat
set NAVER_CLIENT_ID=발급받은_CLIENT_ID
set NAVER_CLIENT_SECRET=발급받은_CLIENT_SECRET
```

OpenDART:

```bat
set OPENDART_API_KEY=발급받은_API_KEY
```

API 키는 Git 저장소에 저장하지 않습니다.

## 아직 하지 않는 것

현재 V1 분석에는 다음이 포함되지 않습니다.

- 유사 과거 재료 발생일의 D+1/D+3/D+5 주가 반응
- 실제 테마 대장주 자동 판별
- 당일 거래대금/상승률 기반 Market Confirmation
- LLM 기반 간접/반사 수혜 추론
- CONFIRMED / WATCH / REJECT 최종 재료 판정
- 매수 타이밍 판단

다음 단계는 `HistoricalReactionAnalyzer -> MarketConfirmationAnalyzer` 순서가 적합합니다.
