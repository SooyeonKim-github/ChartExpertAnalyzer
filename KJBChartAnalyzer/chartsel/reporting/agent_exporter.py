from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


_KJB_METRICS = [
    "Baseline_Status",
    "D5_Status",
    "D5_Selected",
    "d5_policy_version",
    "raw_selection_score",
    "d5_base_score",
    "d5_adjusted_score",
    "overextension_penalty",
    "sector_leader_score",
    "sector_name",
    "sector_composite_score",
    "leader_score",
    "relative_strength_score",
    "relative_strength_grade",
    "relative_strength_weight",
    "technical_score",
    "technical_grade",
    "timing_score",
    "timing_grade",
    "risk_score",
    "risk_level",
    "confluence_score",
    "chase_risk",
    "market_regime",
    "action",
    "trailing_stop",
    "bullish_signals",
    "bearish_signals",
    "market",
    "market_cap",
    "trading_value",
    "volume_universe",
    "source_rank",
]


def _clean(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _split_pipe(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def _candidate_from_row(row: pd.Series) -> dict[str, Any]:
    metrics = {
        key: _clean(row.get(key))
        for key in _KJB_METRICS
        if key in row.index
    }
    return {
        "ticker": str(row.get("ticker", "")).zfill(6),
        "name": str(row.get("name", "")),
        "asof": _clean(row.get("asof")),
        "strategy_score": _clean(row.get("score")),
        "status": _clean(row.get("Status")),
        "action": _clean(row.get("action")),
        "close": _clean(row.get("close")),
        "stop_price": _clean(row.get("stop_price")),
        "strengths": _split_pipe(row.get("top_strengths")),
        "risks": _split_pipe(row.get("top_risks")),
        "expert_metrics": metrics,
    }


def export_agent_candidates(
    table: pd.DataFrame,
    out_dir: str | Path,
    top_n: int = 30,
) -> tuple[Path, Path]:
    """김종봉 스크리닝 결과를 서브에이전트용 JSON/Markdown으로 정리한다."""
    agent_dir = Path(out_dir) / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    if table.empty:
        candidates = table.copy()
    else:
        candidates = table.head(max(0, int(top_n))).copy()

    records = [_candidate_from_row(row) for _, row in candidates.iterrows()]
    payload = {
        "expert": "kimjongbong",
        "strategy": "d5_final_relative_strength_confluence",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "candidate_count": len(records),
        "selection_note": (
            "KJB D+5 FINAL V1: baseline CONFIRMED를 전제로 Selection/Timing 45:55, "
            "Leader/Sector 과열 페널티, overextension<8, D5 score>=70을 적용한다. "
            "Operational CONFIRMED는 D5_CONFIRMED 중 당일 D5 adjusted score TOP3만 사용한다."
        ),
        "candidates": records,
    }

    json_path = agent_dir / "candidates.json"
    md_path = agent_dir / "candidates.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    _write_markdown(payload, md_path)
    return json_path, md_path


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# 김종봉 Agent 분석 후보",
        "",
        f"- 생성일시: {payload['generated_at']}",
        f"- 후보 수: {payload['candidate_count']}",
        "- KJB 정책: D+5 FINAL V1",
        "- Operational CONFIRMED: D5_CONFIRMED 중 Daily Top3",
        "",
    ]

    for rank, candidate in enumerate(payload["candidates"], start=1):
        m = candidate.get("expert_metrics", {})
        lines.extend([
            f"## {rank}. {candidate.get('name', '')} ({candidate.get('ticker', '')})",
            "",
            f"- Status: {candidate.get('status')}",
            f"- Baseline Status: {m.get('Baseline_Status')}",
            f"- D5 Status: {m.get('D5_Status')}",
            f"- D5 Selected: {m.get('D5_Selected')}",
            f"- D5 Adjusted Score: {m.get('d5_adjusted_score')}",
            f"- Raw Selection Score: {m.get('raw_selection_score')}",
            f"- Overextension Penalty: {m.get('overextension_penalty')}",
            f"- Leader Score: {m.get('leader_score')}",
            f"- Sector Leader Score: {m.get('sector_leader_score')}",
            f"- Sector: {m.get('sector_name')}",
            f"- Relative Strength: {m.get('relative_strength_score')}",
            f"- Technical: {m.get('technical_score')}",
            f"- Timing: {m.get('timing_score')}",
            f"- Risk: {m.get('risk_score')}",
            f"- Chase Risk: {m.get('chase_risk')}",
            f"- Action: {candidate.get('action')}",
            f"- Market Regime: {m.get('market_regime')}",
            f"- Close: {candidate.get('close')}",
            f"- Stop: {candidate.get('stop_price')}",
            f"- Strengths: {' / '.join(candidate.get('strengths', [])) or '-'}",
            f"- Risks: {' / '.join(candidate.get('risks', [])) or '-'}",
            "",
        ])

    path.write_text("\n".join(lines), encoding="utf-8")
