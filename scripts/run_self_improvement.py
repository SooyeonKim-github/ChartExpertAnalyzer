from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / ".claude" / "agents"
SKILLS_DIR = ROOT / ".claude" / "skills"
REPORT_DIR = ROOT / "reports" / "self-improvement"
STATE_FILE = ROOT / ".self_improvement_state.json"
DEFAULT_THRESHOLD = 90.0
REVIEWER_SKILL = SKILLS_DIR / "dual-axis-quality-review" / "SKILL.md"


def target_files() -> list[Path]:
    targets: list[Path] = []
    if AGENTS_DIR.exists():
        targets.extend(sorted(AGENTS_DIR.glob("*.md")))
    if SKILLS_DIR.exists():
        targets.extend(sorted(SKILLS_DIR.glob("*/SKILL.md")))
    # The reviewer does not rewrite itself.
    return [p for p in targets if p.resolve() != REVIEWER_SKILL.resolve()]


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"next_index": 0, "history": []}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"next_index": 0, "history": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    result: dict[str, str] = {}
    current_key: str | None = None
    for raw in parts[1].splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if re.match(r"^[A-Za-z0-9_-]+\s*:", line):
            key, value = line.split(":", 1)
            current_key = key.strip()
            result[current_key] = value.strip()
        elif current_key and line.lstrip().startswith("-"):
            item = line.lstrip()[1:].strip()
            result[current_key] = (result[current_key] + "," + item).strip(",")
    return result


def has_any(text_lower: str, terms: list[str]) -> bool:
    return any(term.lower() in text_lower for term in terms)


def auto_review(path: Path, text: str) -> dict[str, Any]:
    """Deterministic 0-100 structural/data-discipline review."""
    fm = parse_frontmatter(text)
    lower = text.lower()
    score = 0.0
    findings: list[str] = []
    blockers: list[str] = []

    # 1) Metadata: 15
    if fm:
        score += 4
    else:
        blockers.append("YAML frontmatter missing")
    if fm.get("name"):
        score += 4
    else:
        blockers.append("frontmatter name missing")
    if fm.get("description"):
        score += 4
    else:
        findings.append("frontmatter description missing")
    if path.parent == AGENTS_DIR:
        if fm.get("model") or "model:" in lower:
            score += 1.5
        if fm.get("tools") or "tools:" in lower:
            score += 1.5
    else:
        expected = path.parent.name
        if fm.get("name") == expected:
            score += 3
        else:
            blockers.append(f"skill name must match directory: {expected}")

    # 2) Role/purpose: 15
    if has_any(lower, ["# 역할", "## 역할", "# 목적", "## 목적", "purpose", "role", "overview"]):
        score += 10
    else:
        findings.append("role/purpose section is unclear")
    if len(text) >= 900:
        score += 5
    else:
        findings.append("instructions are very short")

    # 3) Inputs / use conditions: 15
    if has_any(lower, ["# 입력", "## 입력", "입력 데이터", "when to use", "사용 시점", "사용 조건", "data priority"]):
        score += 10
    else:
        findings.append("input/use conditions are not explicit")
    if has_any(lower, ["데이터", "data", "source_files", "source"]):
        score += 5

    # 4) Workflow/framework: 15
    if has_any(lower, ["workflow", "프레임워크", "분석 순서", "검증 순서", "체크리스트", "핵심 원칙", "분석 프레임워크"]):
        score += 10
    else:
        findings.append("workflow/framework section is unclear")
    numbered = len(re.findall(r"(?m)^\s*(?:\d+\.|###\s+\d+)", text))
    if numbered >= 2:
        score += 5
    else:
        findings.append("workflow has little explicit sequencing")

    # 5) Output contract: 15
    if has_any(lower, ["출력 형식", "출력 계약", "output contract", "output format", "결과"]):
        score += 8
    else:
        findings.append("output contract section missing")
    if "```json" in lower or "```yaml" in lower:
        score += 7
    else:
        findings.append("machine-readable handoff example missing")

    # 6) Guardrails/data discipline: 15
    if has_any(lower, ["금지 사항", "guardrails", "guardrail", "규칙", "critical reminders"]):
        score += 7
    else:
        findings.append("guardrail section missing")
    if has_any(lower, ["임의", "추측", "look-ahead", "lookahead", "데이터가 없", "unknown", "누락", "만들지"]):
        score += 8
    else:
        findings.append("data hallucination / missing-data rule is weak")

    # 7) Maintainability: 10
    if len(text) <= 16000:
        score += 4
    else:
        findings.append("file is very long; consider moving details to references")
    if len(text) >= 700:
        score += 2
    duplicate_ratio = _duplicate_line_ratio(text)
    if duplicate_ratio <= 0.10:
        score += 2
    else:
        findings.append("repeated instruction lines detected")
    if path.parent == AGENTS_DIR:
        if "skills:" in lower:
            score += 2
        else:
            findings.append("agent has no preloaded skills")
    else:
        score += 2

    score = max(0.0, min(100.0, score))
    if blockers:
        score = min(score, 69.0)

    return {
        "score": round(score, 1),
        "blockers": blockers,
        "findings": findings,
        "duplicate_line_ratio": round(duplicate_ratio, 4),
    }


def _duplicate_line_ratio(text: str) -> float:
    lines = [re.sub(r"\s+", " ", x.strip().lower()) for x in text.splitlines()]
    lines = [x for x in lines if len(x) >= 18 and not x.startswith("```")]
    if not lines:
        return 0.0
    return max(0.0, (len(lines) - len(set(lines))) / len(lines))


def claude_path() -> str | None:
    return shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe")


def run_claude(prompt: str) -> str:
    exe = claude_path()
    if not exe:
        raise RuntimeError("Claude Code CLI not found in PATH")
    proc = subprocess.run(
        [exe, "-p", prompt],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"claude exited with {proc.returncode}")
    return proc.stdout.strip()


def llm_review(path: Path, text: str) -> dict[str, Any]:
    prompt = f"""
You are the LLM axis of ChartExpertAnalyzer's quality gate.
Review only the file below. It is a Korean-stock chart-analysis Agent/Skill, not a US-market workflow.
Evaluate role clarity, data discipline, confirmation bias, Korean-market fit, downstream contract quality,
role overlap, contradictions, and maintainability.

Return ONLY strict JSON, no markdown fence:
{{
  "score": 0,
  "blockers": [],
  "strengths": [],
  "improvement_items": [],
  "role_overlap": [],
  "contract_issues": []
}}
Score must be an integer 0-100. A blocker is only a serious issue that can break or corrupt the workflow.

TARGET: {relative(path)}

FILE CONTENT:
{text}
""".strip()
    raw = run_claude(prompt)
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise RuntimeError("Claude review did not return JSON")
    data = json.loads(match.group(0))
    data["score"] = max(0, min(100, int(data.get("score", 0))))
    for key in ["blockers", "strengths", "improvement_items", "role_overlap", "contract_issues"]:
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def combined_score(auto: dict[str, Any], llm: dict[str, Any] | None) -> float:
    if llm is None:
        return float(auto["score"])
    return round(float(auto["score"]) * 0.5 + float(llm["score"]) * 0.5, 1)


def strip_markdown_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def improve_file(path: Path, text: str, review: dict[str, Any], auto: dict[str, Any]) -> str:
    prompt = f"""
Improve the following ChartExpertAnalyzer Agent/Skill markdown.
Return ONLY the COMPLETE replacement markdown file, without code fences or commentary.

Hard constraints:
- Preserve the existing frontmatter `name` exactly.
- Preserve the file's core role; do not convert it to a US-stock/FMP/13F workflow.
- Preserve useful output fields unless a change clearly improves handoff compatibility.
- Never weaken missing-data, no-hallucination, or risk guardrails.
- Remove duplicated wording where possible.
- Make input, workflow, output contract, and guardrails explicit.
- Do not modify any Python Analyzer logic; this task only improves this markdown file.

TARGET: {relative(path)}
AUTO REVIEW:
{json.dumps(auto, ensure_ascii=False, indent=2)}
LLM REVIEW:
{json.dumps(review, ensure_ascii=False, indent=2)}

CURRENT FILE:
{text}
""".strip()
    return strip_markdown_fence(run_claude(prompt))


def same_name(original: str, candidate: str) -> bool:
    return parse_frontmatter(original).get("name") == parse_frontmatter(candidate).get("name")


def write_report(result: dict[str, Any]) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", result["target"])
    json_path = REPORT_DIR / f"review_{stem}_{ts}.json"
    md_path = REPORT_DIR / f"review_{stem}_{ts}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    before = result["before"]
    after = result.get("after")
    lines = [
        "# Self-Improvement Review",
        "",
        f"- Target: `{result['target']}`",
        f"- Mode: `{result['mode']}`",
        f"- Threshold: `{result['threshold']}`",
        f"- Before auto score: `{before['auto']['score']}`",
        f"- Before LLM score: `{before.get('llm', {}).get('score', 'N/A')}`",
        f"- Before final score: `{before['final_score']}`",
        f"- Action: `{result['action']}`",
    ]
    if after:
        lines.extend([
            f"- After auto score: `{after['auto']['score']}`",
            f"- After LLM score: `{after.get('llm', {}).get('score', 'N/A')}`",
            f"- After final score: `{after['final_score']}`",
        ])
    items = before.get("llm", {}).get("improvement_items", []) or before["auto"].get("findings", [])
    if items:
        lines.extend(["", "## Improvement Items", ""])
        lines.extend([f"- {x}" for x in items])
    lines.extend(["", "## Quality Gate", "", result.get("quality_gate_note", "")])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def process_target(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8-sig")
    auto_before = auto_review(path, original)
    llm_before = None
    llm_error = None

    if not args.dry_run:
        try:
            llm_before = llm_review(path, original)
        except Exception as exc:
            llm_error = str(exc)

    before_score = combined_score(auto_before, llm_before)
    result: dict[str, Any] = {
        "target": relative(path),
        "mode": "dry-run" if args.dry_run else ("apply" if args.apply else "review"),
        "threshold": args.threshold,
        "before": {"auto": auto_before, "llm": llm_before, "final_score": before_score},
        "action": "NO_CHANGE",
        "quality_gate_note": "",
    }
    if llm_error:
        result["llm_error"] = llm_error

    if before_score >= args.threshold:
        result["action"] = "PASS"
        result["quality_gate_note"] = "Score already meets threshold."
        return result

    if not args.apply:
        result["action"] = "IMPROVEMENT_RECOMMENDED"
        result["quality_gate_note"] = "Below threshold; run with --apply to generate and gate an improved candidate."
        return result

    if llm_before is None:
        result["action"] = "SKIPPED_NO_LLM"
        result["quality_gate_note"] = "Claude CLI review unavailable; no automatic edit was attempted."
        return result

    candidate = improve_file(path, original, llm_before, auto_before)
    if not candidate or not candidate.startswith("---"):
        result["action"] = "REJECTED_CANDIDATE"
        result["quality_gate_note"] = "Candidate is not a valid frontmatter markdown file. Original kept."
        return result
    if not same_name(original, candidate):
        result["action"] = "REJECTED_NAME_CHANGE"
        result["quality_gate_note"] = "Candidate changed the canonical name. Original kept."
        return result

    auto_after = auto_review(path, candidate)
    llm_after = None
    llm_after_error = None
    try:
        llm_after = llm_review(path, candidate)
    except Exception as exc:
        llm_after_error = str(exc)
    after_score = combined_score(auto_after, llm_after)
    result["after"] = {"auto": auto_after, "llm": llm_after, "final_score": after_score}
    if llm_after_error:
        result["llm_after_error"] = llm_after_error

    before_blockers = set(auto_before.get("blockers", [])) | set((llm_before or {}).get("blockers", []))
    after_blockers = set(auto_after.get("blockers", [])) | set((llm_after or {}).get("blockers", []))
    new_blockers = sorted(after_blockers - before_blockers)
    if new_blockers:
        result["action"] = "REJECTED_NEW_BLOCKER"
        result["new_blockers"] = new_blockers
        result["quality_gate_note"] = "New blocker detected. Original kept."
        return result

    if after_score <= before_score:
        result["action"] = "REJECTED_NO_IMPROVEMENT"
        result["quality_gate_note"] = "Re-score did not improve. Original kept."
        return result

    path.write_text(candidate.rstrip() + "\n", encoding="utf-8")
    result["action"] = "APPLIED"
    result["quality_gate_note"] = f"Candidate improved {before_score} -> {after_score} and passed the no-new-blocker gate."
    return result


def choose_targets(args: argparse.Namespace) -> tuple[list[Path], dict[str, Any]]:
    targets = target_files()
    if not targets:
        raise SystemExit("No .claude Agent/Skill targets found")
    state = load_state()

    if args.target:
        wanted = args.target.replace("\\", "/").lower()
        matched = [p for p in targets if wanted in relative(p).lower() or wanted == p.stem.lower() or wanted == p.parent.name.lower()]
        if not matched:
            raise SystemExit(f"Target not found: {args.target}")
        return [matched[0]], state

    if args.all:
        return targets, state

    index = int(state.get("next_index", 0)) % len(targets)
    return [targets[index]], state


def main() -> None:
    parser = argparse.ArgumentParser(description="ChartExpertAnalyzer Agent/Skill self-improvement loop")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--target", help="partial path, agent name, or skill directory name")
    parser.add_argument("--all", action="store_true", help="review all targets instead of round-robin one target")
    parser.add_argument("--dry-run", action="store_true", help="deterministic review only; no Claude CLI and no edits")
    parser.add_argument("--apply", action="store_true", help="allow Claude-generated candidate to replace a file only after quality gate passes")
    args = parser.parse_args()

    selected, state = choose_targets(args)
    run_results: list[dict[str, Any]] = []
    for target in selected:
        result = process_target(target, args)
        json_report, md_report = write_report(result)
        result["json_report"] = relative(json_report)
        result["md_report"] = relative(md_report)
        run_results.append(result)
        print(f"[{result['action']}] {result['target']} score={result['before']['final_score']}")
        if result.get("after"):
            print(f"  after={result['after']['final_score']}")
        print(f"  report={relative(md_report)}")

    if not args.target and not args.all:
        all_targets = target_files()
        current = selected[0]
        current_index = all_targets.index(current)
        state["next_index"] = (current_index + 1) % len(all_targets)
    history = state.setdefault("history", [])
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    for result in run_results:
        history.append({
            "run_at": now,
            "target": result["target"],
            "before_score": result["before"]["final_score"],
            "after_score": result.get("after", {}).get("final_score"),
            "action": result["action"],
        })
    state["history"] = history[-100:]
    save_state(state)


if __name__ == "__main__":
    main()
