---
name: workflow-integration-test
description: CLAUDE.md에 정의된 Analyzer → Expert → Reviewer → Investment Chief 흐름의 파일 존재, 입력/출력 계약, 필드명, handoff 순서를 점검한다. 멀티 에이전트 구조 변경 후 파이프라인 호환성 검증에 사용한다.
---

# Workflow Integration Test

## 목적

각 Agent가 개별적으로 잘 작성돼 있어도 **handoff가 깨지면 전체 workflow는 실패**한다.

TraderMonty `skill-integration-tester`의 contract 검증 개념을 ChartExpertAnalyzer 구조에 맞게 변형한다.

## 검증 대상

```text
Analyzer output
→ candidate-data-quality
→ siyoon-analyst / kimjongbong-analyst
→ risk-reviewer
→ strategy-reviewer
→ investment-chief
```

## 체크리스트

### 1. File Existence

- `CLAUDE.md`
- `.claude/agents/*.md`
- Agent가 preload하는 `.claude/skills/*/SKILL.md`

### 2. Agent Frontmatter

최소:

- name
- description
- model
- tools 또는 명시적 상속
- skills에 적힌 Skill 이름이 실제로 존재

### 3. Producer / Consumer Contract

다음 필드가 다음 단계에 전달 가능한지 본다.

Expert:
- ticker
- name
- decision
- confidence
- reasons
- risks

Risk:
- ticker
- risk_level
- risk_penalty

Strategy:
- ticker
- consensus_quality
- consensus_multiplier
- duplication_penalty

Chief:
- final_decision
- final_score/confidence
- why_selected
- key_risks

### 4. Naming Consistency

- ticker vs symbol 혼용
- risk_score vs risk_penalty 혼동
- rank 자료형 불일치
- confidence 0~1 vs 0~100 혼용

### 5. Workflow Order

Reviewer가 Expert보다 먼저 실행되거나 Chief가 Review를 건너뛰지 않는지 확인한다.

### 6. Fail-Closed

필수 입력이 없을 때 임의 값으로 계속 진행하는 지침이 없는지 확인한다.

## 결과

```json
{
  "workflow_status": "VALID|WARNING|BROKEN",
  "checked_agents": [],
  "checked_skills": [],
  "broken_handoffs": [],
  "naming_warnings": [],
  "missing_files": [],
  "recommended_fixes": []
}
```

## 사용 시점

- Agent/Skill 파일 추가 후
- 출력 JSON 형식 변경 후
- Analyzer의 `agent_summary.csv` 컬럼 변경 후
- Self-Improvement가 파일을 수정한 후

## Guardrails

- 검증만 수행할 때 Analyzer 로직을 수정하지 않는다.
- 필드가 없으면 호환된다고 가정하지 않는다.
- 문서에 정의되지 않은 암묵적 handoff를 만들지 않는다.

## Source Inspiration

Adapted from TraderMonty's `skill-integration-tester` methodology in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.