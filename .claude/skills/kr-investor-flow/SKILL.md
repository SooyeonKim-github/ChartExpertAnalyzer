---
name: kr-investor-flow
description: 한국 주식의 외국인·기관 순매수 금액/수량과 섹터 수급의 지속성을 해석해 가격·상대강도와 수급이 함께 확인되는지 평가한다. KJB 주도주 분석의 수급 검증에 사용한다.
---

# KR Investor Flow

## 목적

미국 13F가 아니라 한국 시장에서 실제로 활용 가능한 **외국인·기관 순매매**를 이용해 주도주 수급의 지속성과 신뢰도를 검토한다.

TraderMonty `institutional-flow-tracker`의 핵심인 '스마트머니 흐름을 단일 값이 아니라 지속성·집중도·가격 반응과 함께 본다'는 개념만 한국시장용으로 변형했다.

## 입력

데이터가 존재할 때만 다음을 활용한다.

- 외국인 순매수 금액
- 외국인 순매수 수량
- 기관 순매수 금액
- 기관 순매수 수량
- 최근 N일 누적 수급
- 섹터 단위 외국인/기관 수급
- 거래대금
- Selection / RS / 가격 추세

## 분석 프레임워크

### 1. Direction

- 외국인 순매수/순매도
- 기관 순매수/순매도
- 두 주체의 방향 일치 여부

### 2. Persistence

하루 수급보다 연속성과 누적 흐름을 우선한다.

- 1일만 강한 수급
- 3~5일 지속
- 주간 누적
- 최근 흐름의 가속/감속

기간 데이터가 없으면 지속성을 추측하지 않는다.

### 3. Price Confirmation

수급과 가격이 함께 움직이는지 본다.

긍정 예:

- 외국인/기관 누적 순매수 + 상대강도 상승
- 눌림 중 순매도 축소 + 반등 시 순매수 회복

주의 예:

- 대규모 순매수인데 가격이 계속 약함
- 가격 급등인데 외국인/기관이 지속 순매도

### 4. Sector Confirmation

개별 종목 수급이 해당 섹터 수급과 일치하는지 본다.

- 종목 + 섹터 동시 순매수: 신뢰도 보조
- 종목만 강하고 섹터는 지속 유출: 경고

### 5. Concentration

거래대금 대비 순매수 규모가 의미 있는지 본다.
절대 금액만으로 대형주와 중소형주를 같은 기준으로 비교하지 않는다.

## Flow Label

- `STRONG_ACCUMULATION`
- `ACCUMULATION`
- `NEUTRAL`
- `DISTRIBUTION`
- `STRONG_DISTRIBUTION`
- `INSUFFICIENT_DATA`

## 출력 계약

```json
{
  "ticker": "",
  "flow_label": "NEUTRAL",
  "foreign_view": "",
  "institution_view": "",
  "persistence": "",
  "price_confirmation": "",
  "sector_confirmation": "",
  "flow_confidence": 0,
  "warnings": []
}
```

## Guardrails

- 순매수 = 매집이라고 자동 해석하지 않는다.
- 단일 하루 수급으로 장기 기관 포지셔닝을 추정하지 않는다.
- 금액과 수량 데이터를 혼동하지 않는다.
- 수급 데이터가 없으면 뉴스나 추측으로 대체하지 않는다.
- 미국 SEC 13F/FMP 의존성을 사용하지 않는다.

## Source Inspiration

Adapted for Korean equities from the institutional-flow concepts in TraderMonty's `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.