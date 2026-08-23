from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


_SWING_METRICS = [
    "Prob_Mid_Before_Stop",
    "Prob_PriorHigh_Before_Stop",
    "Prob_Upper_Before_Stop",
    "Pullback_Pct",
    "Uptrend_HH_HL",
    "Prior_Low_Held",
    "Channel_Coverage",
    "Channel_Position",
    "Channel_Lower",
    "Channel_Mid",
    "Prior_High_Target",
    "Channel_Upper",
    "Room_To_Mid_Pct",
    "Room_To_Upper_Pct",
    "Double_Bottom",
    "Double_Bottom_Confirmed",
    "MA_Clustered",
    "MA_Spread_Pct",
    "MA_Reclaimed",
    "MA5_Held",
    "Bottom_Volume_Surge",
    "Reference_Date",
    "Reference_Low_Held",
    "Reference_High_Break",
    "Reference_Volume_Ratio",
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
        for key in _SWING_METRICS
        if key in row.index
    }
    return {
        "ticker": str(row.get("Ticker", "")).zfill(6),
        "name": str(row.get("Name", "")),
        "asof": _clean(row.get("Actual_Date")),
        "strategy_score": _clean(row.get("Score")),
        "status": _clean(row.get("Status")),
        "primary_signal": _clean(row.get("Primary_Signal")),
        "close": _clean(row.get("Close")),
        "stop_price": _clean(row.get("Stop_Price")),
        "strengths": _split_pipe(row.get("Reasons")),
        "risks": _split_pipe(row.get("Warnings")),
        "expert_metrics": metrics,
    }


def export_agent_candidates(
    signals: pd.DataFrame,
    out_dir: str | Path,
    top_n: int = 30,
) -> tuple[Path, Path]:
    """시윤주식 스캔 결과를 서브에이전트가 읽기 쉬운 JSON/Markdown으로 정리한다."""
    base_dir = Path(out_dir)
    agent_dir = base_dir / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    if signals.empty:
        candidates = signals.copy()
    else:
        candidates = signals[
            signals["Status"].isin(["CONFIRMED", "WATCH"])
        ].copy()
        candidates = candidates.head(max(0, int(top_n)))

    records = [_candidate_from_row(row) for _, row in candidates.iterrows()]
    payload = {
        "expert": "siyoon",
        "strategy": "swing_pullback_channel",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "candidate_count": len(records),
        "selection_note": "Python 스크리너가 CONFIRMED/WATCH 후보를 정리한 파일이며, 최종 TOP5는 시윤주식 서브에이전트가 판단한다.",
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
        "# 시윤주식 Agent 분석 후보",
        "",
        f"- 생성일시: {payload['generated_at']}",
        f"- 후보 수: {payload['candidate_count']}",
        "- 용도: 이 후보들 중 시윤주식 강의 철학에 가장 부합하는 최종 TOP5 선정",
        "",
    ]

    for rank, candidate in enumerate(payload["candidates"], start=1):
        m = candidate.get("expert_metrics", {})
        lines.extend([
            f"## {rank}. {candidate.get('name', '')} ({candidate.get('ticker', '')})",
            "",
            f"- Status: {candidate.get('status')}",
            f"- Score: {candidate.get('strategy_score')}",
            f"- Primary Signal: {candidate.get('primary_signal')}",
            f"- Close: {candidate.get('close')}",
            f"- Stop: {candidate.get('stop_price')}",
            f"- Channel Position: {m.get('Channel_Position')}",
            f"- Room To Upper: {m.get('Room_To_Upper_Pct')}%",
            f"- Prior High Probability: {m.get('Prob_PriorHigh_Before_Stop')}",
            f"- Upper Probability: {m.get('Prob_Upper_Before_Stop')}",
            f"- Strengths: {' / '.join(candidate.get('strengths', [])) or '-'}",
            f"- Risks: {' / '.join(candidate.get('risks', [])) or '-'}",
            "",
        ])

    path.write_text("\n".join(lines), encoding="utf-8")
