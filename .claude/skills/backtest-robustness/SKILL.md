---
name: backtest-robustness
description: ChartExpertAnalyzer의 스크리닝·매매 조건을 백테스트할 때 과최적화, look-ahead, 표본 부족, 특정 기간 의존성을 점검하고 파라미터 안정구간과 스트레스 테스트를 우선 평가한다.
---

# Backtest Robustness

## 목적

백테스트의 목표를 **가장 높은 과거 수익률 찾기**가 아니라 **조건이 조금 바뀌어도 덜 무너지는 전략 찾기**로 둔다.

TraderMonty `backtest-expert`의 robustness-first 철학을 ChartExpertAnalyzer의 KOSPI/KOSDAQ 스크리닝과 스윙 전략 검증에 맞게 적용한다.

## 사용 시점

- `min-score`, `min-timing`, 이동평균 기간 등 조건을 바꿨을 때
- 특정 월 성능이 갑자기 좋아졌을 때
- 새로운 섹터/수급 필터를 추가했을 때
- 두 Analyzer의 규칙을 비교할 때
- 전략을 실제 후보 선정 workflow에 반영하기 전

## 검증 순서

### 1. Hypothesis

전략의 핵심 가설을 한 문장으로 설명할 수 있어야 한다.

예:

> 상승 추세 주도주가 첫 눌림에서 거래량을 줄이고 지지를 확인하면 이후 일정 기간의 상승 확률이 높다.

가설을 설명하지 못한 채 점수만 조합하지 않는다.

### 2. No Look-Ahead

반드시 확인:

- 진입일 이후 데이터가 조건 계산에 들어가지 않았는가
- 미래 수익률 컬럼으로 후보가 필터링되지 않았는가
- 섹터 랭킹/수급 데이터가 당시 시점에 실제 이용 가능했는가
- 상장폐지·신규상장 등 universe survivorship가 왜곡되지 않았는가

### 3. Sample Size

표본이 작으면 높은 승률도 낮은 신뢰도로 본다.

가이드:

- 30건 미만: 탐색 단계
- 30~99건: 제한적 검증
- 100건 이상: 비교 가능
- 200건 이상: 상대적으로 높은 신뢰

시장/전략 특성에 따라 절대 기준처럼 사용하지 않는다.

### 4. Parameter Plateau

최적값 하나보다 주변 범위가 함께 견조한지 본다.

예:

- `min_score = 68, 70, 72, 75`
- `min_timing = 60, 65, 70`
- MA 허용 이격 또는 눌림 깊이 ±10~25%

딱 하나의 값에서만 성능이 튀면 과최적화 위험을 높인다.

### 5. Time Robustness

- 월별/분기별/연도별
- 상승장/하락장/횡보장
- KOSPI/KOSDAQ
- 섹터별

로 나눠 성능을 확인한다.

특정 한 달 또는 특정 테마에 대부분의 수익이 몰리면 경고한다.

### 6. Friction / Entry Realism

가능한 경우 다음을 보수적으로 적용한다.

- 수수료/세금
- 슬리피지
- 시가 갭
- 거래량 부족
- 당일 종가를 보고 같은 종가에 체결하는 비현실적 가정

### 7. Failure Study

성공 차트만 보지 않는다.

반드시 동일 조건을 만족했지만 실패한 종목에서 다음을 찾는다.

- 과열
- 지지 붕괴
- 거래량 분배
- 섹터 약화
- 시장 대비 RS 약화
- 진입 위치 문제

## 5축 평가

각 0~20점, 총 100점으로 평가할 수 있다.

1. Sample Adequacy
2. Expectancy / Outcome Stability
3. Parameter Robustness
4. Time & Regime Robustness
5. Bias & Execution Realism

## Verdict

- `ROBUST`: 80 이상 + 치명적 오류 없음
- `PROMISING`: 65~79
- `FRAGILE`: 45~64
- `REJECT`: 44 이하 또는 look-ahead 등 치명적 오류

점수보다 치명적 오류가 우선한다.

## 출력 계약

```json
{
  "strategy": "",
  "robustness_score": 0,
  "verdict": "PROMISING",
  "sample_size": 0,
  "plateau_assessment": "",
  "regime_dependence": "",
  "bias_flags": [],
  "stress_tests_needed": [],
  "recommended_next_test": ""
}
```

## Source Inspiration

Adapted from TraderMonty's `backtest-expert` methodology in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.