---
name: kr-sector-leadership
description: KOSPI/KOSDAQ 후보의 섹터 상대강도, 섹터 수급, 종목-섹터 동조성, 섹터 내 리더십을 평가한다. KJBChartAnalyzer의 주도주 후보를 검증할 때 사용한다.
---

# KR Sector Leadership

## 목적

개별 종목의 강세가 **강한 섹터 안의 리더십**인지, 아니면 섹터와 분리된 일회성 급등인지 구분한다.

TraderMonty `sector-analyst`의 상대성과·참여도·사이클 해석 원칙을 한국 주식 섹터 수급 데이터에 맞게 변형했다.

## 입력

가능하면 다음 필드를 사용한다.

- sector
- sector_rs_score
- sector_composite_score
- sector_flow_score
- sector_flow_label
- sector_leader_score
- sector_stock_leader_rank
- foreign / institution flow 관련 압축 지표
- 종목 Selection / RS

필드가 없으면 임의로 생성하지 않고 `unknown`으로 처리한다.

## 분석 프레임워크

### 1. Sector Strength

- 섹터 상대강도
- 최근 섹터 랭킹
- 강세 지속성
- 단기 급등만으로 순위가 왜곡됐는지

### 2. Sector Participation

한두 종목만 강한지, 여러 종목이 함께 강한지 본다.

### 3. Flow Confirmation

수급 데이터가 있을 때만 외국인/기관 방향, 누적 흐름, 가격과 수급의 방향 일치를 확인한다. 수급이 없으면 가격만 보고 매집이라고 표현하지 않는다.

### 4. Stock-in-Sector Leadership

우선순위:
1. Selection 강도
2. Stock RS
3. Sector RS
4. 섹터 내 순위
5. 수급 지속성

### 5. Rotation Risk

- 섹터 전체 약화 중 개별 종목만 급등
- 섹터 상위권이 빠르게 교체
- 동일 테마 후보 집중
- 수급과 가격 방향의 지속 충돌

## 출력 계약

```json
{
  "sector": "",
  "sector_strength": 0,
  "participation": "BROAD|MIXED|NARROW|UNKNOWN",
  "flow_confirmation": "POSITIVE|NEUTRAL|NEGATIVE|UNKNOWN",
  "stock_leadership": "LEADER|STRONG|AVERAGE|WEAK",
  "rotation_risk": "LOW|MEDIUM|HIGH",
  "sector_confidence": 0,
  "reasons": [],
  "warnings": []
}
```

## Guardrails

- 미국 섹터 ETF/FMP 데이터를 요구하지 않는다.
- 한국 시장 내부 데이터만으로 판단한다.
- 단일 하루 수급으로 섹터 추세를 확정하지 않는다.
- 강한 섹터라는 이유만으로 모든 구성 종목을 긍정 평가하지 않는다.

## Source Inspiration

Adapted for Korean equities from TraderMonty's `sector-analyst` methodology in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.
