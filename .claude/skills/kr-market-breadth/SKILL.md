---
name: kr-market-breadth
description: KOSPI/KOSDAQ 분석 유니버스에서 상승 참여도, 이동평균 상단 비율, 섹터 확산도, 리더 집중도를 이용해 시장 참여 폭을 0~100 관점으로 평가한다. 주도주 후보가 시장 전체 참여와 함께 움직이는지 확인할 때 사용한다.
---

# KR Market Breadth

## 목적

상승장이 **시장 전반으로 확산되는지** 아니면 소수 대형주/특정 섹터에만 집중되는지 정량적으로 해석한다.

TraderMonty `market-breadth-analyzer`의 핵심인 참여도·추세·다이버전스·0~100 건강도 개념을 한국 주식 유니버스에 맞게 변형한다.

## 데이터 우선순위

가능하면 Analyzer가 계산한 전체 유니버스 요약값을 사용한다.

권장 입력:

- 분석 종목 수
- 상승 종목 비율
- MA20 위 종목 비율
- MA60 위 종목 비율
- MA120 위 종목 비율
- Selection 기준 통과 비율
- RS 강세 종목 비율
- 강세 섹터 수 / 전체 섹터 수
- 상위 5~10개 종목의 상승 기여 집중도
- KOSPI/KOSDAQ 지수 추세

후보 TOP5만 보고 시장 breadth를 추정하지 않는다.

## 5개 구성 요소

입력 데이터가 있을 때 다음을 0~100으로 상대 평가한다.

1. **Participation Level (30%)**
   - 상승 종목 및 MA 상단 종목 비율
2. **Trend Breadth (25%)**
   - MA20/60/120 참여의 방향과 지속성
3. **Sector Breadth (20%)**
   - 강세가 여러 섹터에 분산되는지
4. **Leader Concentration (15%)**
   - 소수 리더에 과도하게 의존하면 감점
5. **Index Divergence (10%)**
   - 지수 상승과 내부 참여도가 반대로 움직이면 감점

입력 누락 요소는 억지로 0점 처리하지 말고 제외한 뒤 가중치를 재정규화한다.

## Health Zone

- 80~100: `BROAD_STRONG`
- 60~79: `HEALTHY`
- 40~59: `MIXED`
- 20~39: `NARROWING`
- 0~19: `FRAGILE`

이 점수는 시장 수익률 예측치가 아니라 **참여 폭의 건강도**다.

## 활용

- KimJongBong 후보의 리더십이 시장 확산과 함께 나타나는지 확인
- 최종 Investment Chief가 후보 집중 위험을 판단할 때 보조
- breadth가 약해지는 시기에는 추격형 후보 confidence를 보수적으로 조정

Breadth가 낮다고 좋은 개별 종목을 자동 탈락시키지는 않는다.

## 출력 계약

```json
{
  "market": "KOSPI|KOSDAQ|COMBINED",
  "breadth_score": 0,
  "zone": "MIXED",
  "components_used": [],
  "strongest_signal": "",
  "weakest_signal": "",
  "divergence_warning": "",
  "data_warnings": []
}
```

## Guardrails

- S&P 500용 고정 임계값을 한국 시장에 그대로 적용하지 않는다.
- 입력 데이터 기간이 서로 다르면 경고한다.
- 전체 유니버스 정보가 없으면 `INSUFFICIENT_DATA`로 처리한다.
- breadth score를 개별 종목 매수 신호로 사용하지 않는다.

## Source Inspiration

Adapted for Korean equities from TraderMonty's `market-breadth-analyzer` methodology in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.