---
name: dual-axis-quality-review
description: ChartExpertAnalyzer의 Agent와 Skill 문서를 deterministic Auto Axis와 LLM Review Axis 두 축으로 0~100 평가한다. Self-Improvement Loop에서 90점 미만 파일의 개선 필요성을 판정할 때 사용한다.
---

# Dual-Axis Quality Review

## 목적

Agent/Skill 품질을 느낌으로 평가하지 않고 **재현 가능한 구조 점검 + 비판적 LLM 리뷰** 두 축으로 평가한다.

TraderMonty `dual-axis-skill-reviewer`의 품질 게이트 개념을 ChartExpertAnalyzer의 `.claude/agents`와 `.claude/skills`에 맞게 변형했다.

## Axis A: Deterministic Quality (50%)

기계적으로 확인 가능한 항목을 점검한다.

### Metadata

- YAML frontmatter 존재
- name / description 존재
- Agent의 model/tools/skills 구조 유효
- skill name과 디렉토리명 일관성

### Role Clarity

- 역할 또는 목적이 명확함
- 입력 범위 정의
- 분석/Workflow 정의
- 출력 계약 정의
- 금지사항/Guardrail 존재

### Contract Quality

- JSON/YAML output 예시 또는 명확한 필드 계약
- confidence/score 범위 정의
- 데이터 누락 처리 규칙
- 다음 단계 handoff 필드 식별 가능

### Safety / Data Discipline

- 데이터 없는 사실 생성 금지
- look-ahead/날짜 불일치 등 데이터 위험 고려
- 역할 범위 밖 행동 제한

## Axis B: LLM Deep Review (50%)

다음 질문으로 0~100 평가한다.

1. 이 파일의 역할이 다른 Agent/Skill과 불필요하게 중복되는가?
2. 입력 데이터보다 강한 결론을 내리도록 유도하는가?
3. 긍정 신호만 강화하는 확인편향이 있는가?
4. 출력 계약이 downstream에서 실제 사용 가능한가?
5. 모순되거나 실행 불가능한 지침이 있는가?
6. 한국 주식 데이터 구조와 맞지 않는 미국시장 전용 가정이 남아 있는가?
7. 더 짧고 명확하게 만들면서 품질을 높일 부분이 있는가?

## Final Score

```text
final_score = auto_score × 0.5 + llm_score × 0.5
```

치명적 contract 오류가 있으면 평균 점수와 별개로 `BLOCKER`를 지정할 수 있다.

## Quality Gate

- 90~100: `PASS`
- 80~89: `IMPROVE`
- 70~79: `REWORK`
- 0~69: `CRITICAL_REVIEW`

Self-Improvement에서는 기본 threshold를 90으로 사용한다.

## 출력 계약

```json
{
  "target": "",
  "auto_score": 0,
  "llm_score": 0,
  "final_score": 0,
  "verdict": "PASS",
  "blockers": [],
  "strengths": [],
  "improvement_items": [],
  "role_overlap": [],
  "contract_issues": []
}
```

## 개선 후 Quality Gate

수정 후보는 반드시 다시 같은 기준으로 평가한다.

채택 조건:

1. blocker가 새로 생기지 않음
2. final_score가 기존보다 상승
3. 핵심 역할과 output contract가 보존됨
4. 다른 Agent/Skill handoff를 깨지 않음

조건을 만족하지 않으면 기존 파일을 유지한다.

## Source Inspiration

Adapted from TraderMonty's `dual-axis-skill-reviewer` and Self-Improvement Loop concepts in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.