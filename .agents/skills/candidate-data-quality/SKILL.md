---
name: candidate-data-quality
description: 멀티 에이전트 실행 전에 Agent 후보 JSON/Markdown 및 후보 CSV의 날짜, 티커, 중복, 결측, 숫자 범위, 컬럼 일관성을 점검한다. 잘못된 입력으로 Expert가 과신하지 않게 하는 사전 품질 게이트다.
---

# Candidate Data Quality

## 목적

Codex 분석 이전에 **입력 데이터가 믿을 만한지** 먼저 확인한다.

TraderMonty `data-quality-checker`의 pre-flight 검증 개념을 ChartExpertAnalyzer의 JSON/CSV handoff에 맞게 변형했다.

## 우선 점검

### 1. Freshness
- run_date / 데이터 기준일 존재 여부
- Swing과 KJB 결과 기준일 일치 여부
- 파일명 날짜와 내부 날짜 불일치 여부

### 2. Identifier
- ticker 빈 값/형식 불일치
- 동일 ticker에 서로 다른 종목명
- 중복 행

### 3. Missing Critical Fields
각 Analyzer가 요구하는 핵심 필드가 빠졌는지 확인한다. 없는 필드를 0으로 간주하지 않는다.

### 4. Numeric Sanity
- NaN / inf
- score 정의 범위 밖
- 음수가 될 수 없는 값의 음수
- percentage와 ratio 단위 혼동
- 비정상 문자열 숫자

### 5. Cross-file Consistency
같은 ticker가 두 Analyzer에 있을 때 종목명, 기준일, 시장 구분, sector 충돌 여부를 본다.

### 6. Size / Context Budget
Expert 입력은 후보 위주로 압축되어야 한다. 전체 OHLCV, 불필요한 수백 컬럼, 수천~수만 행 원본, 장문 중복은 경고한다.

## Severity

- `ERROR`: 분석 중단 또는 해당 행 제외 가능성이 큼
- `WARNING`: 분석 가능하지만 confidence 하향
- `INFO`: 참고

## Output Contract

```json
{
  "status": "PASS|WARNING|FAIL",
  "source_files": [],
  "row_count": 0,
  "findings": [
    {
      "severity": "WARNING",
      "category": "freshness",
      "message": ""
    }
  ],
  "excluded_tickers": [],
  "confidence_modifier": 1.0
}
```

## Gate Rule

- `FAIL`: Expert 실행 전에 입력 수정 또는 문제 종목 제외
- `WARNING`: Expert 실행 가능, confidence 반영
- `PASS`: 정상 진행

## Guardrails

- 결측치를 임의 평균/0으로 채우지 않는다.
- 날짜가 없으면 오늘 데이터라고 가정하지 않는다.
- 서로 다른 단위를 같은 값으로 비교하지 않는다.
- 데이터 품질 문제와 종목 투자 매력을 혼동하지 않는다.

## Source Inspiration

Adapted from TraderMonty's `data-quality-checker` methodology in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.
