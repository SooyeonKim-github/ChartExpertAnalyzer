# ChartExpertAnalyzer Codex Multi-Agent Guide

이 저장소는 Python Analyzer가 먼저 후보를 계산하고, Codex의 전문 Subagent들이 서로 다른 관점으로 후보를 독립 검토한 뒤 최종 후보를 선정하는 구조를 사용한다.

## 핵심 목표

단순히 Analyzer 점수가 높은 종목을 고르는 것이 아니라 다음을 구분한다.

- 좋은 종목인가
- 지금 진입하기 좋은 위치인가
- 두 Expert의 추천 근거가 실제로 독립적인가
- 현재 하방 위험과 데이터 신뢰도는 관리 가능한가

최종 TOP5는 강제로 채우지 않는다.

## 프로젝트 구성

Analyzer:

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

Codex custom agents:

- `.codex/agents/siyoon-analyst.toml`
- `.codex/agents/kimjongbong-analyst.toml`
- `.codex/agents/risk-reviewer.toml`
- `.codex/agents/strategy-reviewer.toml`
- `.codex/agents/investment-chief.toml`

Codex skills:

- `.agents/skills/technical-chart-analysis/SKILL.md`
- `.agents/skills/kr-sector-leadership/SKILL.md`
- `.agents/skills/kr-investor-flow/SKILL.md`
- `.agents/skills/kr-market-breadth/SKILL.md`
- `.agents/skills/backtest-robustness/SKILL.md`
- `.agents/skills/candidate-data-quality/SKILL.md`
- `.agents/skills/position-sizing/SKILL.md`
- `.agents/skills/consensus-ranking/SKILL.md`
- `.agents/skills/workflow-integration-test/SKILL.md`
- `.agents/skills/dual-axis-quality-review/SKILL.md`
- `.agents/skills/self-improvement-loop/SKILL.md`

## Analyzer 실행과 Agent 실행은 분리한다

`run_all_screen.bat`은 Python Analyzer 두 개를 실행하고 Agent용 후보 파일을 생성한다.

이 BAT 자체가 Codex Subagent를 실행하는 것은 아니다.

Analyzer 결과:

```text
KJBChartAnalyzer/
└─ output/
   └─ agent/
      ├─ candidates.json
      └─ candidates.md

SwingChartProbabilityAnalyzer/
└─ results/
   └─ YYYYMMDD/
      └─ agent/
         ├─ candidates.json
         └─ candidates.md
```

멀티에이전트 분석을 요청받으면 가장 최근의 위 파일을 우선 사용한다.

## 멀티에이전트 Workflow

사용자가 다음처럼 요청하면 Codex subagents를 사용한다.

- 오늘 종목 분석해줘
- 멀티에이전트로 분석해줘
- 두 Analyzer 결과 종합해줘
- 최종 TOP5 뽑아줘
- 시윤과 김종봉 관점으로 같이 봐줘

실행 순서:

```text
Analyzer candidates
        │
        ▼
 candidate-data-quality
        │
   ┌────┴────┐
   ▼         ▼
siyoon-    kimjongbong-
analyst     analyst
   │         │
   └────┬────┘
        ▼
  risk-reviewer
        ▼
 strategy-reviewer
        ▼
 investment-chief
        ▼
     최종 TOP5
```

### 1. Data Quality

먼저 `$candidate-data-quality` 원칙으로 입력을 점검한다.

필수 확인:

- 기준일
- ticker/종목명
- 중복
- 핵심 필드 결측
- 숫자 범위 이상
- 두 Analyzer 기준일 불일치

FAIL 수준의 데이터 오류가 있으면 잘못된 행을 제외하거나 문제를 명시한다. 없는 값을 임의로 0으로 채우지 않는다.

### 2. Expert 병렬 실행

`siyoon-analyst`와 `kimjongbong-analyst`를 서로의 결과를 보여주지 않은 상태에서 가능하면 병렬 subagent로 실행한다.

두 Expert가 끝날 때까지 기다린 후 다음 단계로 진행한다.

#### siyoon-analyst

입력:

`SwingChartProbabilityAnalyzer/results/<latest>/agent/candidates.json`

핵심 질문:

> 지금 이 자리에서 상승추세 눌림목 스윙 진입을 검토하기 좋은가?

필요 Skill:

- `$technical-chart-analysis`
- `$candidate-data-quality`

#### kimjongbong-analyst

입력:

`KJBChartAnalyzer/output/agent/candidates.json`

핵심 질문:

> 시장이 실제로 선택한 주도주이며 현재 Timing도 합리적인가?

필요 Skill:

- `$technical-chart-analysis`
- `$kr-sector-leadership`
- `$kr-investor-flow`
- `$kr-market-breadth`
- `$candidate-data-quality`

### 3. 후보 합집합

두 Expert의 추천 종목 합집합만 Reviewer에 전달한다.

새 종목을 Reviewer가 추가로 발굴하게 하지 않는다.

### 4. Risk Review

`risk-reviewer`가 후보 합집합만 검토한다.

검토:

- Chase Risk
- 추세/지지 구조 훼손
- 손절/무효화 기준 명확성
- 거래량 분배 위험
- 변동성
- 동일 섹터 집중
- 데이터 위험

Risk Reviewer는 새로운 매수 후보를 추천하지 않는다.

### 5. Strategy Review

`strategy-reviewer`가 Expert 추천의 독립성을 검토한다.

중요:

두 Expert가 같은 종목을 추천했다고 자동으로 2표로 계산하지 않는다.

다음은 상관된 신호일 수 있다.

- 상승 추세 ↔ 상대강도
- 거래량 증가 ↔ 거래대금 증가 ↔ Selection
- 돌파 강도 ↔ Leader Score
- 눌림 후 재상승 ↔ Timing

분류:

- `STRONG_INDEPENDENT`
- `MODERATE`
- `CORRELATED`
- `CONFLICTED`
- `SINGLE_EXPERT`

### 6. Investment Chief

`investment-chief`가 모든 결과를 종합한다.

개념:

```text
Expert Strength
+ Independent Consensus
+ Entry Quality
+ Data Confidence
- Risk Penalty
- Strategy Duplication Penalty
```

최종 판단:

- `BUY_CANDIDATE`
- `WATCH`
- `WAIT_PULLBACK`
- `OVERHEATED`
- `AVOID`

단순 수학식만으로 결정하지 않는다.

## 입력 데이터 원칙

Expert/Subagent는 기본적으로 압축 후보 데이터만 읽는다.

사용자가 별도로 요청하지 않으면 통째로 읽지 않는다.

- 전체 OHLCV 원본
- 전체 종목 장기 시계열
- 대규모 range backtest
- 수만 행 이벤트 로그
- 대량 차트 이미지

Python Analyzer는 계산/스크리닝을 담당하고 Codex Agent는 압축 후보의 의미를 해석한다.

## 데이터에 없는 사실 금지

다음 값이 입력에 없으면 추측하지 않는다.

- 뉴스
- 실적
- 목표주가
- 외국인/기관 수급
- 섹터
- RSI/MA 등 특정 기술지표 값

데이터가 없으면 `unknown`, `INSUFFICIENT_DATA` 또는 confidence 하향으로 처리한다.

## 좋은 종목과 좋은 위치를 구분한다

예:

```text
강한 주도주
+ 높은 상대강도
+ 강한 섹터
BUT
최근 급등 + MA 이격 과다
→ WAIT_PULLBACK
```

이 판단은 정상이다.

## 분석 요청과 코드 수정 요청을 분리한다

사용자가 주식 후보 분석만 요청했으면 Analyzer Python 코드, 설정, BAT를 수정하지 않는다.

코드 변경은 사용자가 명시적으로 요청한 경우에만 수행한다.

## Backtest 검증

전략/파라미터 개선 요청에서는 필요할 때 `$backtest-robustness`를 사용한다.

최고 과거수익 한 점보다 다음을 우선한다.

- look-ahead 방지
- 충분한 표본
- parameter plateau
- 기간/레짐 안정성
- 슬리피지/체결 현실성
- 실패 사례 분석

## Workflow 변경 검증

Agent/Skill의 출력 계약이나 경로를 변경했으면 `$workflow-integration-test`를 사용해 다음을 확인한다.

- custom agent TOML 존재
- Skill 존재
- Producer/Consumer JSON 필드 호환
- ticker/name/confidence/risk 필드 일관성
- Expert → Risk → Strategy → Chief 순서

## Self-Improvement

Agent/Skill 품질 점검은 `$self-improvement-loop`와 `scripts/run_self_improvement.py`를 사용한다.

대상:

- `.codex/agents/*.toml`
- `.agents/skills/*/SKILL.md`

Analyzer Python 코드는 Self-Improvement가 자동 수정하지 않는다.

기본 품질 임계값은 90점이다.

점수가 낮다고 자동으로 나쁜 파일로 교체하지 않는다. 개선 후보를 다시 평가하고 점수가 실제로 상승하며 새 blocker가 없을 때만 채택한다.

## 최종 출력 원칙

사용자에게는 내부 장문 분석보다 다음을 우선한다.

```text
최종 TOP 후보
1. 종목명 — BUY_CANDIDATE
   핵심 이유: ...
   Expert 의견: ...
   Risk: ...
   진입 관점: ...

현재 기다리는 편이 좋은 종목
- 종목명 — WAIT_PULLBACK: ...

전체 주의사항
- 섹터 집중
- 데이터 누락
- 시장 참여도 등
```

가능하면 structured JSON 결과도 유지한다.
