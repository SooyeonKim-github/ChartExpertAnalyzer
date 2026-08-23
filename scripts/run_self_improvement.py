from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover - fallback for older local Python
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / ".codex" / "agents"
SKILLS_DIR = ROOT / ".agents" / "skills"
REPORT_DIR = ROOT / "reports" / "self-improvement"
STATE_FILE = ROOT / ".self_improvement_state.json"
DEFAULT_THRESHOLD = 90.0
REVIEWER_SKILL = SKILLS_DIR / "dual-axis-quality-review" / "SKILL.md"


def target_files() -> list[Path]:
    targets: list[Path] = []
    if AGENTS_DIR.exists():
        targets.extend(sorted(AGENTS_DIR.glob("*.toml")))
    if SKILLS_DIR.exists():
        targets.extend(sorted(SKILLS_DIR.glob("*/SKILL.md")))
    return [p for p in targets if p.resolve() != REVIEWER_SKILL.resolve()]


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"next_index": 0, "history": []}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"next_index": 0, "history": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_agent(path: Path) -> bool:
    return path.suffix.lower() == ".toml" and path.parent == AGENTS_DIR


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
            result[current_key] = value.strip().strip('"').strip("'")
        elif current_key and line.lstrip().startswith("-"):
            item = line.lstrip()[1:].strip()
            result[current_key] = (result[current_key] + "," + item).strip(",")
    return result


def _fallback_parse_agent_toml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ["name", "description", "model", "model_reasoning_effort", "sandbox_mode"]:
        match = re.search(
            rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"\s*$',
            text,
        )
        if match:
            result[key] = match.group(1)
    dev = re.search(
        r'(?s)developer_instructions\s*=\s*"""(.*?)"""',
        text,
    )
    if dev:
        result["developer_instructions"] = dev.group(1)
    return result


def parse_agent_toml(text: str) -> tuple[dict[str, Any], str | None]:
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
            return data, None
        except Exception as exc:
            return _fallback_parse_agent_toml(text), str(exc)
    data = _fallback_parse_agent_toml(text)
    if not data:
        return {}, "TOML parser unavailable and fallback parser found no fields"
    return data, None


def canonical_name(path: Path, text: str) -> str | None:
    if is_agent(path):
        data, _ = parse_agent_toml(text)
        value = data.get("name")
        return str(value) if value is not None else None
    return parse_frontmatter(text).get("name")


def has_any(text_lower: str, terms: list[str]) -> bool:
    return any(term.lower() in text_lower for term in terms)


def _duplicate_line_ratio(text: str) -> float:
    lines = [re.sub(r"\s+", " ", x.strip().lower()) for x in text.splitlines()]
    lines = [x for x in lines if len(x) >= 18 and not x.startswith("```")]
    if not lines:
        return 0.0
    return max(0.0, (len(lines) - len(set(lines))) / len(lines))


def auto_review(path: Path, text: str) -> dict[str, Any]:
    """Deterministic 0-100 review for Codex agent TOML or Codex skill Markdown."""
    findings: list[str] = []
    blockers: list[str] = []
    score = 0.0

    if is_agent(path):
        metadata, parse_error = parse_agent_toml(text)
        body = str(metadata.get("developer_instructions", ""))
        lower = body.lower()

        if parse_error:
            blockers.append(f"agent TOML parse warning/error: {parse_error}")
        else:
            score += 3

        if metadata.get("name"):
            score += 4
        else:
            blockers.append("agent name missing")
        if metadata.get("description"):
            score += 4
        else:
            blockers.append("agent description missing")
        if body.strip():
            score += 4
        else:
            blockers.append("developer_instructions missing")
    else:
        fm = parse_frontmatter(text)
        body = text
        lower = text.lower()
        if fm:
            score += 3
        else:
            blockers.append("skill YAML frontmatter missing")
        if fm.get("name"):
            score += 4
        else:
            blockers.append("skill name missing")
        if fm.get("description"):
            score += 4
        else:
            blockers.append("skill description missing")
        expected = path.parent.name
        if fm.get("name") == expected:
            score += 4
        else:
            blockers.append(f"skill name must match directory: {expected}")

    # Role / purpose: 15
    if has_any(lower, ["# 역할", "## 역할", "역할", "# 목적", "## 목적", "목적", "purpose", "role", "핵심 질문"]):
        score += 10
    else:
        findings.append("role/purpose is unclear")
    if len(body) >= 700:
        score += 5
    else:
        findings.append("instructions are very short")

    # Inputs / use conditions: 15
    if has_any(lower, ["입력", "input", "기본 입력", "사용 조건", "사용 시점", "data priority", "source_files"]):
        score += 10
    else:
        findings.append("input/use conditions are not explicit")
    if has_any(lower, ["데이터", "data", "candidate", "source", "ticker"]):
        score += 5
    else:
        findings.append("data/source expectations are weak")

    # Workflow / framework: 15
    if has_any(lower, ["workflow", "프레임워크", "분석 순서", "검토 항목", "검증 순서", "평가 순서", "핵심 원칙", "분석 순서"]):
        score += 10
    else:
        findings.append("workflow/framework is unclear")
    numbered = len(re.findall(r"(?m)^\s*(?:\d+\.|###\s+\d+)", body))
    if numbered >= 2:
        score += 5
    else:
        findings.append("workflow has little explicit sequencing")

    # Output contract: 15
    if has_any(lower, ["출력", "output", "결과", "return"]):
        score += 8
    else:
        findings.append("output contract is unclear")
    if "{" in body and "}" in body and ('"ticker"' in body or '"target"' in body or '"system"' in body or '"reviewer"' in body):
        score += 7
    else:
        findings.append("machine-readable handoff example is missing or weak")

    # Guardrails / data discipline: 15
    if has_any(lower, ["금지", "guardrail", "규칙", "하지 않는다", "금지 사항"]):
        score += 7
    else:
        findings.append("guardrails are weak")
    if has_any(lower, ["임의", "추측", "데이터에 없", "데이터가 없", "unknown", "누락", "만들지", "look-ahead", "lookahead"]):
        score += 8
    else:
        findings.append("missing-data / hallucination rule is weak")

    # Maintainability / Codex fit: 10
    duplicate_ratio = _duplicate_line_ratio(body)
    if len(body) <= 16000:
        score += 3
    else:
        findings.append("instructions are very long")
    if duplicate_ratio <= 0.10:
        score += 2
    else:
        findings.append("repeated instruction lines detected")

    if is_agent(path):
        metadata, _ = parse_agent_toml(text)
        if "$" in body:
            score += 2
        else:
            findings.append("agent does not reference any Codex skill; verify this is intentional")
        if metadata.get("sandbox_mode") == "read-only":
            score += 2
        else:
            findings.append("read-only analysis agent does not explicitly use sandbox_mode=read-only")
        if metadata.get("description") and len(str(metadata.get("description"))) >= 20:
            score += 1
    else:
        if "source inspiration" in lower or "source" in lower:
            score += 2
        else:
            score += 1
        if "## guardrails" in lower or "guardrails" in lower or "규칙" in lower:
            score += 2
        if len(body) >= 700:
            score += 1

    score = max(0.0, min(100.0, score))
    if blockers:
        score = min(score, 69.0)

    return {
        "artifact_type": "agent_toml" if is_agent(path) else "skill_markdown",
        "score": round(score, 1),
        "blockers": blockers,
        "findings": findings,
        "duplicate_line_ratio": round(duplicate_ratio, 4),
    }


def codex_path() -> str | None:
    return (
        shutil.which("codex")
        or shutil.which("codex.cmd")
        or shutil.which("codex.exe")
    )


def run_codex(prompt: str) -> str:
    exe = codex_path()
    if not exe:
        raise RuntimeError(
            "Codex CLI not found in PATH. Install/sign in to Codex CLI first."
        )
    proc = subprocess.run(
        [exe, "exec", "--ephemeral", "--sandbox", "read-only", prompt],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.strip() or f"codex exec exited with {proc.returncode}"
        )
    return proc.stdout.strip()


def llm_review(path: Path, text: str) -> dict[str, Any]:
    artifact_type = "Codex custom-agent TOML" if is_agent(path) else "Codex SKILL.md"
    prompt = f"""
You are the LLM axis of ChartExpertAnalyzer's quality gate.
Review ONLY the artifact embedded below. It belongs to a Korean-stock chart-analysis project.
Do not inspect or modify repository files.

Artifact type: {artifact_type}
Evaluate role clarity, data discipline, confirmation bias, Korean-market fit,
downstream contract quality, role overlap, contradictions, Codex compatibility,
and maintainability.

Return ONLY strict JSON, with no markdown fence:
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

ARTIFACT CONTENT:
{text}
""".strip()
    raw = run_codex(prompt)
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise RuntimeError("Codex review did not return strict JSON")
    data = json.loads(match.group(0))
    data["score"] = max(0, min(100, int(data.get("score", 0))))
    for key in [
        "blockers",
        "strengths",
        "improvement_items",
        "role_overlap",
        "contract_issues",
    ]:
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def combined_score(auto: dict[str, Any], llm: dict[str, Any] | None) -> float:
    if llm is None:
        return float(auto["score"])
    return round(float(auto["score"]) * 0.5 + float(llm["score"]) * 0.5, 1)


def strip_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def improve_file(
    path: Path,
    text: str,
    review: dict[str, Any],
    auto: dict[str, Any],
) -> str:
    if is_agent(path):
        format_rules = """
Return a COMPLETE valid Codex custom-agent TOML file.
Preserve the existing `name` exactly.
The resulting TOML must contain `name`, `description`, and `developer_instructions`.
Keep analysis/reviewer agents read-only unless the existing role clearly requires writes.
Preserve useful `$skill-name` guidance when relevant.
Do not return Markdown or YAML frontmatter.
""".strip()
    else:
        format_rules = """
Return a COMPLETE Codex SKILL.md Markdown file.
Preserve the YAML frontmatter `name` exactly and keep a useful `description`.
Do not return TOML.
""".strip()

    prompt = f"""
Improve the embedded ChartExpertAnalyzer artifact using the reviews below.
Return ONLY the COMPLETE replacement file, without code fences or commentary.
Do not inspect or modify repository files.

FORMAT RULES:
{format_rules}

HARD CONSTRAINTS:
- Preserve the artifact's core role and Korean-stock focus.
- Do not introduce US-only FMP/13F assumptions.
- Preserve useful output fields unless a change clearly improves handoff compatibility.
- Never weaken missing-data, no-hallucination, or risk guardrails.
- Remove duplicated wording where possible.
- Make input, workflow, output contract, and guardrails explicit.
- Do not modify Analyzer Python logic; only improve this Agent/Skill artifact.

TARGET: {relative(path)}
AUTO REVIEW:
{json.dumps(auto, ensure_ascii=False, indent=2)}
LLM REVIEW:
{json.dumps(review, ensure_ascii=False, indent=2)}

CURRENT ARTIFACT:
{text}
""".strip()
    return strip_fence(run_codex(prompt))


def candidate_is_valid(path: Path, original: str, candidate: str) -> tuple[bool, str]:
    original_name = canonical_name(path, original)
    candidate_name = canonical_name(path, candidate)
    if not candidate_name:
        return False, "candidate canonical name is missing"
    if original_name != candidate_name:
        return False, "candidate changed the canonical name"

    if is_agent(path):
        data, error = parse_agent_toml(candidate)
        if error:
            return False, f"candidate TOML parse failed: {error}"
        for key in ["name", "description", "developer_instructions"]:
            if not data.get(key):
                return False, f"candidate agent missing required field: {key}"
        return True, ""

    if not candidate.startswith("---"):
        return False, "candidate SKILL.md has no YAML frontmatter"
    fm = parse_frontmatter(candidate)
    if not fm.get("description"):
        return False, "candidate skill description is missing"
    return True, ""


def write_report(result: dict[str, Any]) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", result["target"])
    json_path = REPORT_DIR / f"review_{stem}_{ts}.json"
    md_path = REPORT_DIR / f"review_{stem}_{ts}.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    before = result["before"]
    after = result.get("after")
    before_llm = before.get("llm") or {}
    lines = [
        "# Self-Improvement Review",
        "",
        f"- Target: `{result['target']}`",
        f"- Mode: `{result['mode']}`",
        f"- Threshold: `{result['threshold']}`",
        f"- Before auto score: `{before['auto']['score']}`",
        f"- Before LLM score: `{before_llm.get('score', 'N/A')}`",
        f"- Before final score: `{before['final_score']}`",
        f"- Action: `{result['action']}`",
    ]
    if after:
        after_llm = after.get("llm") or {}
        lines.extend(
            [
                f"- After auto score: `{after['auto']['score']}`",
                f"- After LLM score: `{after_llm.get('score', 'N/A')}`",
                f"- After final score: `{after['final_score']}`",
            ]
        )

    items = before_llm.get("improvement_items", []) or before["auto"].get(
        "findings", []
    )
    if items:
        lines.extend(["", "## Improvement Items", ""])
        lines.extend([f"- {x}" for x in items])
    lines.extend(
        ["", "## Quality Gate", "", result.get("quality_gate_note", "")]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def process_target(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8-sig")
    auto_before = auto_review(path, original)
    llm_before: dict[str, Any] | None = None
    llm_error: str | None = None

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
        "before": {
            "auto": auto_before,
            "llm": llm_before,
            "final_score": before_score,
        },
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
        result["quality_gate_note"] = (
            "Below threshold; run with --apply to generate and gate an improved candidate."
        )
        return result

    if llm_before is None:
        result["action"] = "SKIPPED_NO_LLM"
        result["quality_gate_note"] = (
            "Codex CLI review unavailable; no automatic edit was attempted."
        )
        return result

    candidate = improve_file(path, original, llm_before, auto_before)
    valid, reason = candidate_is_valid(path, original, candidate)
    if not valid:
        result["action"] = "REJECTED_CANDIDATE"
        result["quality_gate_note"] = reason + ". Original kept."
        return result

    auto_after = auto_review(path, candidate)
    llm_after: dict[str, Any] | None = None
    llm_after_error: str | None = None
    try:
        llm_after = llm_review(path, candidate)
    except Exception as exc:
        llm_after_error = str(exc)

    after_score = combined_score(auto_after, llm_after)
    result["after"] = {
        "auto": auto_after,
        "llm": llm_after,
        "final_score": after_score,
    }
    if llm_after_error:
        result["llm_after_error"] = llm_after_error

    before_blockers = set(auto_before.get("blockers", [])) | set(
        (llm_before or {}).get("blockers", [])
    )
    after_blockers = set(auto_after.get("blockers", [])) | set(
        (llm_after or {}).get("blockers", [])
    )
    new_blockers = sorted(after_blockers - before_blockers)
    if new_blockers:
        result["action"] = "REJECTED_NEW_BLOCKER"
        result["new_blockers"] = new_blockers
        result["quality_gate_note"] = "New blocker detected. Original kept."
        return result

    if llm_after is None:
        result["action"] = "REJECTED_NO_REVIEW"
        result["quality_gate_note"] = (
            "Improved candidate could not be re-reviewed by Codex. Original kept."
        )
        return result

    if after_score <= before_score:
        result["action"] = "REJECTED_NO_IMPROVEMENT"
        result["quality_gate_note"] = (
            "Re-score did not improve. Original kept."
        )
        return result

    path.write_text(candidate.rstrip() + "\n", encoding="utf-8")
    result["action"] = "APPLIED"
    result["quality_gate_note"] = (
        f"Candidate improved {before_score} -> {after_score} and passed the no-new-blocker gate."
    )
    return result


def choose_targets(args: argparse.Namespace) -> tuple[list[Path], dict[str, Any]]:
    targets = target_files()
    if not targets:
        raise SystemExit("No Codex Agent/Skill targets found")
    state = load_state()

    if args.target:
        wanted = args.target.replace("\\", "/").lower()
        matched = [
            p
            for p in targets
            if wanted in relative(p).lower()
            or wanted == p.stem.lower()
            or wanted == p.parent.name.lower()
        ]
        if not matched:
            raise SystemExit(f"Target not found: {args.target}")
        return [matched[0]], state

    if args.all:
        return targets, state

    index = int(state.get("next_index", 0)) % len(targets)
    return [targets[index]], state


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ChartExpertAnalyzer Codex Agent/Skill self-improvement loop"
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--target", help="partial path, agent name, or skill directory name"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="review all targets instead of one round-robin target",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="deterministic review only; no Codex CLI and no edits",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="allow Codex-generated candidate to replace a file only after the quality gate passes",
    )
    args = parser.parse_args()

    selected, state = choose_targets(args)
    run_results: list[dict[str, Any]] = []
    for target in selected:
        result = process_target(target, args)
        json_report, md_report = write_report(result)
        result["json_report"] = relative(json_report)
        result["md_report"] = relative(md_report)
        run_results.append(result)
        print(
            f"[{result['action']}] {result['target']} "
            f"score={result['before']['final_score']}"
        )
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
        history.append(
            {
                "run_at": now,
                "target": result["target"],
                "before_score": result["before"]["final_score"],
                "after_score": result.get("after", {}).get("final_score"),
                "action": result["action"],
            }
        )
    state["history"] = history[-100:]
    save_state(state)


if __name__ == "__main__":
    main()
