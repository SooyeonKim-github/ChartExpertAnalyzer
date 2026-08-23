---
name: workflow-integration-test
description: AGENTS.md에 정의된 Analyzer → Expert → Reviewer → Investment Chief 흐름의 Codex agent/skill 존재, 입력·출력 계약, 필드명, handoff 순서를 점검한다. 멀티 에이전트 구조 변경 후 파이프라인 호환성 검증에 사용한다.
---

# Workflow Integration Test

## 목적

각 Agent가 개별적으로 잘 작성돼 있어도 **handoff가 깨지면 전체 workflow는 실패**한다.

TraderMonty `skill-integration-tester`의 contract 검증 개념을 ChartExpertAnalyzer의 Codex 구조에 맞게 변형한다.

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

- `AGENTS.md`
- `.codex/config.toml`
- `.codex/agents/*.toml`
- `.agents/skills/*/SKILL.md`

### 2. Custom Agent TOML

각 `.codex/agents/*.toml` 최소 필드:

- `name`
- `description`
- `developer_instructions`

선택적으로 `model_reasoning_effort`, `sandbox_mode`가 의도와 맞는지 확인한다.
Agent instruction에서 참조하는 `$skill-name`이 실제 `.agents/skills/<skill-name>/SKILL.md`로 존재하는지 확인한다.

### 3. Producer / Consumer Contract

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
- evidence_relation
- duplication_penalty
- conflicts

Chief:
- final_decision
- final_score/confidence
- evidence_relation
- why_selected
- key_risks

중요:
- 동일 종목이 두 Expert에 동시에 존재한다는 사실 자체는 별도 점수 필드나 보너스 계약으로 사용하지 않는다.
- `consensus_multiplier`, `consensus_quality` 같은 과거 합의 우대 필드를 필수 계약으로 요구하지 않는다.

### 4. Naming Consistency

- ticker vs symbol 혼용
- risk_score vs risk_penalty 혼동
- rank 자료형 불일치
- confidence 0~1 vs 0~100 혼용
- evidence_relation 필드명 일관성

### 5. Workflow Order

Reviewer가 Expert보다 먼저 실행되거나 Chief가 Review를 건너뛰지 않는지 확인한다.

### 6. Fail-Closed

필수 입력이 없을 때 임의 값을 만들어 계속 진행하는 지침이 없는지 확인한다.

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
- Analyzer Agent 후보 구조 변경 후
- Self-Improvement가 Agent/Skill을 수정한 후

## Guardrails

- 검증만 수행할 때 Analyzer 로직을 수정하지 않는다.
- 필드가 없으면 호환된다고 가정하지 않는다.
- 문서에 정의되지 않은 암묵적 handoff를 만들지 않는다.

## Source Inspiration

Adapted from TraderMonty's `skill-integration-tester` methodology in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.
