# ChartExpertAnalyzer Multi-Agent Guide

이 저장소는 서로 다른 주식 차트 분석 철학을 독립적으로 평가한 뒤, 리스크와 전략 중복을 검토하고 최종 후보를 선정하는 멀티 에이전트 구조를 사용한다.

## 목표

최종 목표는 단순한 점수 순위가 아니라 다음 질문에 답하는 것이다.

> 지금 시점에서 어떤 종목이 가장 좋은 **후보**이며, 어떤 종목은 좋아 보여도 현재 위치에서는 기다려야 하는가?

분석은 반드시 **종목의 질**과 **현재 진입 위치**를 구분한다.

---

# 프로젝트 구성

주요 Analyzer:

- `SwingChartProbabilityAnalyzer/`
  - 상승 추세
  - 눌림
  - 지지
  - 반등
  - 거래량
  - 스윙 진입 위치

- `KJBChartAnalyzer/`
  - Selection
  - 시장 대비 상대강도
  - 주도주
  - 섹터 강도
  - 섹터 수급
  - Timing

멀티 에이전트:

- `.claude/agents/siyoon-analyst.md`
- `.claude/agents/kimjongbong-analyst.md`
- `.claude/agents/risk-reviewer.md`
- `.claude/agents/strategy-reviewer.md`
- `.claude/agents/investment-chief.md`

---

# 전체 분석 Workflow

사용자가 다음과 같이 요청하면 멀티 에이전트 분석을 수행한다.

예:

- 오늘 종목 분석해줘
- 두 Analyzer 결과 종합해줘
- 최종 TOP5 뽑아줘
- 멀티 에이전트 돌려줘
- 스윙 후보와 주도주 후보를 같이 봐줘

기본 실행 순서는 다음과 같다.

```text
Analyzer 결과
   │
   ├───────────────┐
   ▼               ▼
siyoon-analyst   kimjongbong-analyst
   │               │
   └───────┬───────┘
           ▼
      risk-reviewer
           │
           ▼
    strategy-reviewer
           │
           ▼
     investment-chief
           │
           ▼
       최종 TOP5
```

---

# 1단계: 입력 데이터 확인

먼저 두 Analyzer의 Agent용 결과 파일을 찾는다.

우선 찾을 파일:

```text
SwingChartProbabilityAnalyzer/**/agent_summary.csv
SwingChartProbabilityAnalyzer/**/agent_meta.json
KJBChartAnalyzer/**/agent_summary.csv
KJBChartAnalyzer/**/agent_meta.json
```

아직 `agent_summary`가 없는 경우 다음 이름을 가진 **소형 후보 결과 파일**을 탐색한다.

```text
*candidate*.csv
*summary*.csv
*screen*.csv
*ranking*.csv
```

후보 파일 선택 시 다음을 우선한다.

1. 최신 실행 결과
2. 후보 종목만 압축된 파일
3. 컬럼이 분석에 필요한 수준으로 정리된 파일
4. 행 수가 과도하지 않은 파일

사용한 파일 경로는 최종 결과에 남긴다.

## 읽지 않는 데이터

사용자가 명시적으로 요청하지 않는 한 다음 파일을 Expert에게 통째로 읽히지 않는다.

- 전체 OHLCV
- 전체 종목 장기 시계열
- 대규모 백테스트 상세 결과
- 수만 행 이벤트 로그
- 이미지/차트가 대량 포함된 결과

목적은 **Python Analyzer가 먼저 계산하고, LLM Agent는 압축된 후보를 해석하도록 하는 것**이다.

---

# 2단계: Expert 분석

가능하면 다음 두 Expert를 **서로 독립적으로 병렬 실행**한다.

## siyoon-analyst

대상:

`SwingChartProbabilityAnalyzer`

핵심 관점:

- 상승 추세
- 건강한 눌림
- 지지선
- 반등 확인
- 거래량 수축/재확대
- 추격 위험

질문:

> 지금 이 자리에서 스윙 진입을 검토하기 좋은가?

## kimjongbong-analyst

대상:

`KJBChartAnalyzer`

핵심 관점:

- Selection
- Stock Relative Strength
- Sector Strength
- Sector Flow
- Leader Quality
- Timing
- Chase Risk

질문:

> 시장이 실제로 선택하고 있는 주도주인가?

## Expert 독립성

두 Expert는 서로의 결과를 먼저 보지 않는다.

한 Expert의 결론이 다른 Expert의 판단에 영향을 주면 멀티 에이전트 구조의 의미가 약해진다.

각 Expert는 최대 TOP5만 반환한다.

TOP5를 억지로 채우지 않는다.

---

# 3단계: 후보 합집합 생성

두 Expert가 추천한 종목의 합집합을 만든다.

예:

```text
Siyoon
삼성전자
SK하이닉스
현대차

KimJongBong
SK하이닉스
한미반도체
삼성전자
```

Reviewer 검토 대상:

```text
삼성전자
SK하이닉스
현대차
한미반도체
```

이 단계에서 단순 투표 수로 순위를 만들지 않는다.

---

# 4단계: Risk Review

`risk-reviewer`에게 Expert 후보의 합집합만 전달한다.

검토 항목:

- 추격 위험
- 구조 훼손 위험
- 손절 기준 명확성
- 거래량 분배 위험
- 변동성
- 동일 섹터 집중
- 데이터 누락/불일치

Risk Reviewer는 새로운 종목을 발굴하지 않는다.

결과에는 최소 다음을 포함한다.

- `risk_level`
- `risk_score`
- `risk_penalty`
- 핵심 위험
- 무효화 기준 힌트

---

# 5단계: Strategy Review

`strategy-reviewer`는 **추천 표의 독립성**을 검토한다.

중요:

> Siyoon과 KimJongBong이 같은 종목을 추천했다고 무조건 2표로 계산하지 않는다.

예를 들어 다음은 서로 다른 이름이지만 같은 모멘텀을 반복 평가했을 가능성이 있다.

```text
상승 추세
상대강도
모멘텀 점수
Selection
거래량 증가
```

Strategy Reviewer는 다음을 구분한다.

- `STRONG_INDEPENDENT`
- `MODERATE`
- `CORRELATED`
- `CONFLICTED`
- `SINGLE_EXPERT`

그리고 다음을 반환한다.

- `consensus_multiplier`
- `duplication_penalty`
- 독립 근거
- 중복 신호
- Expert 간 충돌

---

# 6단계: Investment Chief

마지막으로 `investment-chief`가 모든 결과를 종합한다.

개념적으로 다음 구조를 사용한다.

```text
Expert Strength
+ Independent Consensus
+ Entry Quality
+ Data Confidence
- Risk Penalty
- Strategy Duplication Penalty
```

단순 수학식으로 기계적으로 결정하지 않는다.

입력 데이터가 없는 값을 임의로 만들지 않는다.

최종 판단 라벨:

- `BUY_CANDIDATE`
- `WATCH`
- `WAIT_PULLBACK`
- `OVERHEATED`
- `AVOID`

---

# 최종 출력 원칙

사용자에게는 장문의 내부 분석을 전부 보여주기보다 핵심 결과를 요약한다.

권장 형식:

```text
최종 TOP 후보

1. 종목명 — BUY_CANDIDATE
   왜 선택: ...
   Expert 의견: ...
   Risk: ...
   진입 관점: ...

2. 종목명 — WATCH
   ...

기다리는 편이 좋은 종목
- 종목명 — WAIT_PULLBACK

전체 주의사항
- 특정 섹터 집중
- 데이터 누락
- 시장 변동성 등
```

가능하면 최종 JSON 결과도 함께 유지한다.

---

# 분석 품질 규칙

## 데이터에 없는 사실을 만들지 않는다

특히 다음을 추측하지 않는다.

- 뉴스
- 실적
- 목표주가
- 외국인/기관 수급
- 섹터
- 특정 기술지표 값

데이터가 없으면 `unknown` 또는 데이터 부족으로 처리한다.

## Score는 참고값이다

Python Analyzer가 만든 score는 강한 사전 신호지만 최종 투자 판단 자체가 아니다.

다음처럼 처리한다.

```text
Python
→ 계산 / 스크리닝 / 후보 압축

Expert Agent
→ 패턴 해석

Reviewer
→ 위험 / 중복 검증

Investment Chief
→ 최종 종합
```

## 좋은 종목과 좋은 위치를 구분한다

예:

```text
시장 주도주
+ 상대강도 매우 높음
+ 강한 섹터

BUT

최근 급등
+ MA20 이격 과다

→ WAIT_PULLBACK
```

이 판단은 정상이다.

## TOP5 강제 금지

조건에 맞는 종목이 2개면 2개만 반환한다.

좋지 않은 종목을 채워 넣어 TOP5 숫자를 맞추지 않는다.

---

# 코드 수정 원칙

사용자가 멀티 에이전트 **분석**만 요청한 경우 Analyzer의 Python 코드나 설정을 수정하지 않는다.

코드 수정은 사용자가 명시적으로 다음과 같이 요청할 때만 수행한다.

- 로직 고쳐줘
- 파일 추가해줘
- Analyzer 개선해줘
- GitHub에 반영해줘

분석 실행과 코드 변경을 분리한다.

---

# 향후 Agent Exporter 규격

각 Analyzer에는 최종적으로 다음 형태의 Agent 전달용 파일을 만드는 것을 권장한다.

```text
Analyzer/
└─ results/
   └─ agent/
      ├─ agent_summary.csv
      └─ agent_meta.json
```

## agent_summary.csv

원칙:

- 후보 종목만 포함
- 20~40개 내외 핵심 컬럼
- 불필요한 긴 텍스트 제거
- 전체 시계열 제거
- Expert 판단에 필요한 계산 결과만 포함

## agent_meta.json

권장 항목:

```json
{
  "analyzer": "",
  "run_date": "",
  "market": "",
  "candidate_count": 0,
  "source_period": "",
  "notes": []
}
```

---

# 멀티 에이전트의 핵심 철학

이 프로젝트의 목적은 여러 AI에게 같은 질문을 반복해서 다수결을 만드는 것이 아니다.

각 Agent가 **서로 다른 역할**을 수행해야 한다.

```text
Siyoon
→ 좋은 스윙 차트인가?

KimJongBong
→ 시장이 선택한 주도주인가?

Risk Reviewer
→ 이 종목은 어디서 크게 잘못될 수 있는가?

Strategy Reviewer
→ 여러 추천이 정말 독립된 근거인가?

Investment Chief
→ 그래서 지금 최종적으로 무엇을 우선할 것인가?
```

이 역할 분리를 유지한다.
