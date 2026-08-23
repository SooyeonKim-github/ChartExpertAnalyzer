---
name: position-sizing
description: 최종 후보의 진입가와 무효화/손절 기준이 주어졌을 때 계좌 위험 한도, 손절폭, 변동성을 이용해 적정 비중을 계산한다. 후보 선정과 포지션 크기를 분리하기 위한 리스크 관리 스킬이다.
---

# Position Sizing

## 목적

좋은 종목을 찾는 것과 **얼마나 살 것인지**를 분리한다.

TraderMonty `position-sizer`의 fixed-fractional, ATR 기반, 집중도 제한 원칙을 한국 주식 현물 매매에 맞게 단순화한다.

## 사용 조건

다음 값이 있을 때만 구체적 수량/비중을 계산한다.

- 계좌 평가금액
- 진입 예정 가격
- 손절/무효화 가격 또는 ATR
- 1회 거래 허용 위험률

필수값이 없으면 숫자를 임의로 만들지 않고 계산식을 안내한다.

## 기본 방식

### Fixed Fractional

```text
허용손실금액 = 계좌금액 × 거래위험률
주당위험 = 진입가 - 손절가
매수가능수량 = floor(허용손실금액 / 주당위험)
```

한국 주식은 기본적으로 정수 주식 수를 사용한다.

## 권장 위험 가이드

- 기본 1회 거래 위험: 계좌의 0.5~1.0%
- 높은 변동성/불확실성: 더 낮게
- 2% 초과는 특별한 근거 없이는 권장하지 않음

이는 고정 규칙이 아니라 보수적 기본값이다.

## ATR 방식

ATR이 있으면 손절 거리를 변동성에 맞출 수 있다.

```text
stop_distance = ATR × multiplier
```

ATR multiplier는 백테스트 없이 특정 값 하나를 절대값처럼 사용하지 않는다.

## Portfolio Constraints

최종 수량은 다음 중 가장 보수적인 제한을 따른다.

- 거래별 위험 한도
- 종목 최대 비중
- 동일 섹터 최대 비중
- 현재 오픈 포지션 전체 위험

같은 반도체/2차전지 등 상관된 후보가 여러 개면 개별 위험을 단순 합산하지 말고 집중 위험을 함께 본다.

## 출력 계약

```json
{
  "method": "FIXED_FRACTIONAL|ATR_BASED|INSUFFICIENT_INPUT",
  "account_size": 0,
  "entry_price": 0,
  "stop_price": 0,
  "risk_pct": 0,
  "risk_per_share": 0,
  "shares": 0,
  "position_value": 0,
  "planned_loss": 0,
  "binding_constraint": "",
  "warnings": []
}
```

## Guardrails

- 손절가가 진입가보다 높거나 같으면 long sizing을 계산하지 않는다.
- 손절 기준 없는 종목에 수량부터 제시하지 않는다.
- Kelly 방식은 충분한 검증 통계가 없으면 사용하지 않는다.
- 후보 rank가 높다고 위험 한도를 자동 확대하지 않는다.
- 포지션 사이징은 수익 보장이 아니라 손실 통제 도구다.

## Source Inspiration

Adapted for Korean equities from TraderMonty's `position-sizer` methodology in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.