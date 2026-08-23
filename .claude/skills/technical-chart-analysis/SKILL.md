---
name: technical-chart-analysis
description: 한국 주식의 일봉/주봉 후보 차트를 추세, 지지·저항, 이동평균, 거래량, 눌림과 돌파 관점으로 구조화해 검토한다. 시윤식 스윙 후보와 최종 후보의 기술적 구조 검증에 사용한다.
---

# Technical Chart Analysis

## 목적

한국 주식 후보를 뉴스나 펀더멘털 추측 없이 **관측 가능한 가격·거래량·기술지표**만으로 검토한다.

TraderMonty `technical-analyst`의 체계적 기술분석 원칙을 ChartExpertAnalyzer의 일봉 중심 스윙 분석에 맞게 변형했다.

## 핵심 원칙

1. 추세와 현재 진입 위치를 분리한다.
2. 단일 지표보다 추세·지지·거래량의 합류(confluence)를 본다.
3. 상승/횡보/하락 시나리오를 함께 고려해 확인편향을 줄인다.
4. 데이터에 없는 가격 수준이나 패턴을 만들지 않는다.
5. 모든 긍정 시나리오에는 무효화 조건이 있어야 한다.

## 입력

우선 사용:

- Analyzer가 계산한 `agent_summary.csv`
- `agent_meta.json`
- 후보 종목의 압축 기술지표
- 사용자가 명시적으로 제공한 차트

기본적으로 전체 OHLCV 장기 원본을 통째로 읽지 않는다.

## 분석 순서

### 1. Trend

- MA20/60/120 위치와 기울기
- 고점·저점 방향
- 정배열/역배열
- 중기 추세 훼손 여부

### 2. Support / Resistance

- 최근 스윙 고점·저점
- 이전 돌파 가격
- 박스권 상·하단
- MA20/60/120 동적 지지
- 여러 기준이 겹치는 가격대

### 3. Volume

- 상승 시 거래량 확대 여부
- 눌림 시 거래량 수축 여부
- 재상승 시 거래량 회복 여부
- 고점 대량거래·장대음봉·윗꼬리 분배 위험

### 4. Setup Quality

다음 패턴을 구분한다.

- 건강한 상승 후 눌림
- 돌파 전 압축
- 돌파 후 첫 눌림
- 지지 확인 반등
- 단순 급등/추격
- 장기 하락 중 기술적 반등

### 5. Scenario

최소 Base/Bull/Bear 관점을 내부적으로 비교한다.
확률 숫자가 데이터로 뒷받침되지 않으면 억지로 정밀한 확률을 만들지 않는다.

## 출력 계약

후보별로 최소 다음을 제공한다.

```json
{
  "trend": "UP|SIDEWAYS|DOWN",
  "setup": "PULLBACK|BREAKOUT|REBOUND|EXTENDED|BROKEN",
  "support_view": "",
  "volume_view": "",
  "entry_quality": "GOOD|WATCH|POOR",
  "invalidation": "",
  "technical_confidence": 0,
  "warnings": []
}
```

`technical_confidence`는 0~100 상대 신뢰도이며 데이터 누락 시 낮춘다.

## Guardrails

- 보이지 않는 뉴스·실적·수급을 기술적 근거처럼 사용하지 않는다.
- 목표주가를 임의 생성하지 않는다.
- RSI, MA, 거래량 등 값이 입력에 없으면 있다고 가정하지 않는다.
- 좋은 종목이라도 과열 위치면 진입 품질을 낮춘다.

## Source Inspiration

Adapted for Korean equities from TraderMonty's `technical-analyst` methodology in `claude-trading-skills` (MIT License). See repository `THIRD_PARTY_NOTICES.md`.