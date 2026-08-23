---
name: dual-axis-quality-review
description: ChartExpertAnalyzer의 Codex Agent와 Skill 문서를 deterministic Auto Axis와 Codex LLM Review Axis 두 축으로 0~100 평가한다. Self-Improvement Loop에서 90점 미만 파일의 개선 필요성을 판정할 때 사용한다.
---

# Dual-Axis Quality Review

## 목적

Agent/Skill 품질을 느낌으로 평가하지 않고 **재현 가능한 구조 점검 + 비판적 Codex 리뷰** 두 축으로 평가한다.

TraderMonty `dual-axis-skill-reviewer`의 품질 게이트 개념을 ChartExpertAnalyzer의 Codex 구조에 맞게 변형했다.

## 검토 대상

- `.codex/agents/*.toml`
- `.agents/skills/*/SKILL.md`

Analyzer의 Python 코드와 결과 데이터는 이 품질 리뷰의 자동 수정 대상이 아니다.

## Axis A: Deterministic Quality (50%)

### Codex Agent TOML

기계적으로 다음을 확인한다.

- `name`
- `description`
- `developer_instructions`
- 역할/입력 범위가 명확한지
- 출력 계약 또는 structured 결과 형식이 있는지
- 데이터 누락/추측 금지 규칙이 있는지
- 필요한 Skill을 `$skill-name`으로 명시했는지
- `sandbox_mode = "read-only"` 등 역할에 맞는 실행 범위인지

### Codex Skill Markdown

- YAML frontmatter 존재
- `name` / `description` 존재
- 디렉토리명과 skill name 일치
- 목적/입력/Workflow/출력 계약/Guardrail 존재
- 데이터 누락 처리 규칙 존재

## Axis B: Codex LLM Deep Review (50%)

다음을 비판적으로 평가한다.

1. 역할이 다른 Agent/Skill과 불필요하게 중복되는가
2. 입력 데이터보다 강한 결론을 내리도록 유도하는가
3. 확인편향이나 낙관편향을 강화하는가
4. downstream handoff에서 실제 사용 가능한 출력인가
5. 서로 모순되거나 실행 불가능한 지침이 있는가
6. 한국 주식 프로젝트에 미국시장 전용 가정이 남아 있는가
7. Codex 전용 경로와 실행 방식에 맞는가
8. 더 짧고 명확하게 만들면서 품질을 높일 부분이 있는가

## Final Score

```text
final_score = auto_score × 0.5 + llm_score × 0.5
```

치명적 contract 오류가 있으면 평균점수와 별개로 `BLOCKER`를 지정할 수 있다.

## Quality Gate

- 90~100: `PASS`
- 80~89: `IMPROVE`
- 70~79: `REWORK`
- 0~69: `CRITICAL_REVIEW`

Self-Improvement 기본 threshold는 90이다.

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

수정 후보는 반드시 같은 기준으로 재평가한다.

채택 조건:

1. 새 blocker 없음
2. canonical `name` 보존
3. 핵심 역할 보존
4. final_score 상승
5. Agent ↔ Skill ↔ Reviewer handoff를 깨지 않음

조건을 만족하지 않으면 기존 파일을 유지한다.

## Guardrails

- 높은 점수를 만들기 위해 지침을 장황하게 늘리지 않는다.
- 투자 성과를 품질 점수로 추정하지 않는다.
- Analyzer 전략 로직을 이 리뷰가 자동 수정하지 않는다.
- Codex Agent TOML과 Skill Markdown의 형식 차이를 같은 기준으로 억지 평가하지 않는다.

## Source Inspiration

Adapted from TraderMonty's `dual-axis-skill-reviewer` and Self-Improvement Loop concepts in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.
