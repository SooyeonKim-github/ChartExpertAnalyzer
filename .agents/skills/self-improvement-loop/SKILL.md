---
name: self-improvement-loop
description: ChartExpertAnalyzer의 Codex Agent/Skill 품질을 round-robin으로 점검하고 90점 미만이면 Codex CLI로 개선 후보를 만든 뒤 재평가하여 점수가 실제로 상승한 경우에만 적용한다.
---

# Self-Improvement Loop

## 목적

Agent/Skill을 한 번 만들고 방치하지 않고 정기적으로 **검토 → 개선 후보 생성 → 재검증 → 안전한 채택**을 반복한다.

TraderMonty `claude-trading-skills`의 Self-Improvement Loop를 Windows + Codex 기반 ChartExpertAnalyzer에 맞게 변형했다.

## 기본 Workflow

1. **Round-robin 선택**
   - `.codex/agents/*.toml`
   - `.agents/skills/*/SKILL.md`
   - `dual-axis-quality-review`는 자기 자신을 자동 수정하지 않는다.

2. **Auto Axis 평가**
   - Agent TOML 필수 필드 또는 Skill YAML frontmatter
   - 역할/목적
   - 입력 규칙
   - workflow
   - output contract
   - guardrail
   - 데이터 discipline

3. **Codex LLM Axis 평가**
   - `codex exec`가 논리적 모순, 역할 중복, 확인편향, 한국시장 적합성, handoff 문제를 비판적으로 검토한다.

4. **90점 Gate**
   - 90 이상: 변경 없음
   - 90 미만: 개선 후보 생성 가능

5. **재평가**
   - 개선 후보를 Auto + Codex LLM 두 축으로 다시 평가한다.

6. **채택 조건**
   - 새 blocker 없음
   - canonical `name` 보존
   - 핵심 역할/형식 보존
   - 최종 점수가 기존보다 상승

7. **실패 시 원본 유지**

8. **리포트 저장**
   - `reports/self-improvement/`

## 실행 전제

- Python이 PATH에 있어야 한다.
- Codex CLI의 `codex` 명령이 PATH에 있어야 한다.
- Codex CLI에 로그인된 상태여야 한다.
- Claude Code 또는 Claude API는 필요하지 않다.

## 실행

### deterministic 점검만

```bat
python scripts\run_self_improvement.py --dry-run
```

### Codex 리뷰만, 파일 수정 없음

```bat
python scripts\run_self_improvement.py
```

### 개선 후보 생성 + Quality Gate 통과 시 적용

```bat
python scripts\run_self_improvement.py --apply
```

또는 루트:

```bat
run_self_improvement.bat
```

기본 BAT는 한 target을 round-robin으로 선택하고 `--apply`로 실행한다.

### 특정 Agent/Skill

```bat
python scripts\run_self_improvement.py --target siyoon --apply
python scripts\run_self_improvement.py --target backtest-robustness --apply
```

### 전체 deterministic 점검

```bat
python scripts\run_self_improvement.py --all --dry-run
```

## Windows 자동 실행

필요하면 Windows Task Scheduler에서 `run_self_improvement.bat`를 매일 또는 주 1회 실행하도록 등록한다.
Analyzer 실행과 겹치지 않는 시간대를 사용한다.

자동 Git push/PR은 이 버전에 포함하지 않는다. 로컬 변경은 Git diff로 검토한 뒤 사람이 commit/push한다.

## State

Round-robin 상태:

```text
.self_improvement_state.json
```

## Quality Reports

```text
reports/self-improvement/
├─ review_*.json
└─ review_*.md
```

## 안전 규칙

- Analyzer Python 로직은 이 루프가 자동 수정하지 않는다.
- 대상은 `.codex/agents`와 `.agents/skills`뿐이다.
- 점수가 낮아졌으면 절대 교체하지 않는다.
- 새 blocker가 생기면 교체하지 않는다.
- 미국시장 전용 FMP/13F/ETF 가정이 새로 들어오면 regression으로 본다.
- 자동 개선은 투자 성능 향상을 보장하지 않는다. Agent/Skill 지침 품질만 관리한다.

## Source Inspiration

Adapted from TraderMonty's Self-Improvement Loop and `dual-axis-skill-reviewer` in `claude-trading-skills` (MIT License). See `THIRD_PARTY_NOTICES.md`.
