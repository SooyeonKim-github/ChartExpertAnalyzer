---
name: consensus-ranking
description: 서로 다른 Expert의 추천 순위와 confidence를 결합하되 같은 원천 신호의 중복투표를 감점하고 Risk Reviewer 결과를 반영해 최종 합의 강도를 산정한다.
---

# Consensus Ranking

## 목적

멀티 에이전트의 장점을 단순 다수결로 훼손하지 않는다.

`trend_pullback`과 `market_leader`처럼 서로 다른 Strategy Family의 독립 근거를 인정하되, 같은 모멘텀·거래량 신호가 여러 이름으로 반복 계산된 경우 합의 강도를 낮춘다.

## 입력

- Siyoon Expert TOP 후보
- KimJongBong Expert TOP 후보
- 각 Expert confidence
- Risk Reviewer의 risk penalty
- Strategy Reviewer의 consensus quality / duplication penalty
- Data Quality 결과

## 기본 원칙

### Expert Strength

Expert별 rank와 confidence를 비교한다.
순위 1위와 2위의 차이를 과도하게 확대하지 않는다.

### Independent Consensus

다음처럼 구분한다.

- `STRONG_INDEPENDENT`
- `MODERATE`
- `CORRELATED`
- `CONFLICTED`
- `SINGLE_EXPERT`

두 Expert가 같은 종목을 골랐다는 사실만으로 `STRONG_INDEPENDENT`가 되지 않는다.

### Duplication

중복 가능 신호:

- 상승률 ↔ RS ↔ momentum
- 거래량 증가 ↔ 거래대금 증가 ↔ Selection
- MA 정배열 ↔ trend score
- 돌파 강도 ↔ leader score

### Risk

위험은 마지막에 설명만 붙이는 것이 아니라 최종 ranking에 실제로 반영한다.

### Data Confidence

입력 날짜 불일치, 핵심 필드 결측, 섹터 미매핑이 있으면 최종 confidence를 낮춘다.

## 보조 계산식

입력값이 충분할 때만 다음 개념식을 사용할 수 있다.

```text
adjusted_strength = base_strength × consensus_multiplier
final_score = adjusted_strength - risk_penalty - duplication_penalty
```

없는 값을 임의로 만들어 식을 완성하지 않는다.

## 출력 계약

```json
{
  "ticker": "",
  "expert_strength": 0,
  "consensus_quality": "MODERATE",
  "consensus_multiplier": 0.9,
  "risk_penalty": 0,
  "duplication_penalty": 0,
  "data_confidence": 0,
  "final_score": 0,
  "ranking_reasons": [],
  "warnings": []
}
```

## Guardrails

- 단순 추천 횟수로 점수를 만들지 않는다.
- 한 Expert만 추천했다고 자동 탈락시키지 않는다.
- 서로 충돌하는 의견은 숨기지 않는다.
- 수학식 결과와 설명이 모순되면 설명과 원자료를 재검토한다.