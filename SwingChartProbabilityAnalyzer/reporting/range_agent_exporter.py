from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


_MILESTONES = (5, 10, 20, 40, 60)


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


def _safe_mean(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return round(float(values.mean()), 3) if not values.empty else None


def _safe_rate(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return round(float(values.mean()), 4)


def _milestone_stats(frame: pd.DataFrame, day: int) -> dict[str, Any]:
    ret_col = f"D+{day}_Close_Return_Pct"
    complete_col = f"Forward_Complete_{day}D"
    mfe_col = f"MFE_{day}D_Pct"
    mae_col = f"MAE_{day}D_Pct"

    if ret_col not in frame.columns:
        return {
            "day": day,
            "complete_count": 0,
            "win_rate": None,
            "avg_return_pct": None,
            "median_return_pct": None,
            "avg_mfe_pct": None,
            "avg_mae_pct": None,
        }

    valid_mask = pd.to_numeric(frame[ret_col], errors="coerce").notna()
    if complete_col in frame.columns:
        valid_mask &= pd.to_numeric(frame[complete_col], errors="coerce").fillna(0).eq(1)
    valid = frame.loc[valid_mask]
    returns = pd.to_numeric(valid[ret_col], errors="coerce").dropna()

    return {
        "day": day,
        "complete_count": int(len(returns)),
        "win_rate": round(float((returns > 0).mean()), 4) if not returns.empty else None,
        "avg_return_pct": round(float(returns.mean()), 3) if not returns.empty else None,
        "median_return_pct": round(float(returns.median()), 3) if not returns.empty else None,
        "avg_mfe_pct": _safe_mean(valid[mfe_col]) if mfe_col in valid.columns else None,
        "avg_mae_pct": _safe_mean(valid[mae_col]) if mae_col in valid.columns else None,
    }


def _aggregate(frame: pd.DataFrame, milestones: list[int]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "signal_count": int(len(frame)),
        "milestones": [_milestone_stats(frame, day) for day in milestones],
    }
    if "Hit_Upper_Before_Stop" in frame.columns:
        out["upper_before_stop_rate"] = _safe_rate(frame["Hit_Upper_Before_Stop"])
    if "Hit_PriorHigh_Before_Stop" in frame.columns:
        out["prior_high_before_stop_rate"] = _safe_rate(frame["Hit_PriorHigh_Before_Stop"])
    if "Stop_Hit" in frame.columns:
        out["stop_hit_rate"] = _safe_rate(frame["Stop_Hit"])
    return out


def _grouped(frame: pd.DataFrame, group_col: str, milestones: list[int], limit: int | None = None) -> list[dict[str, Any]]:
    if frame.empty or group_col not in frame.columns:
        return []
    rows: list[dict[str, Any]] = []
    for key, grp in frame.groupby(group_col, dropna=False):
        row = {group_col: _clean(key)}
        row.update(_aggregate(grp, milestones))
        rows.append(row)
    rows.sort(key=lambda x: x.get("signal_count", 0), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return rows


def export_range_agent_summary(
    candidates: pd.DataFrame,
    out_dir: str | Path,
    range_start: str,
    range_end: str,
    forward_bars: int,
) -> tuple[Path, Path]:
    """과거 range 결과를 Codex Agent가 읽기 쉬운 소형 JSON/Markdown으로 압축한다."""
    agent_dir = Path(out_dir) / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    frame = candidates.copy()
    milestones = [d for d in _MILESTONES if d <= int(forward_bars)]
    if int(forward_bars) not in milestones:
        milestones.append(int(forward_bars))
    milestones = sorted(set(milestones))

    if not frame.empty and "Score" in frame.columns:
        score = pd.to_numeric(frame["Score"], errors="coerce")
        frame["Score_Band"] = (score // 5 * 5).astype("Int64")

    ticker_history = _grouped(frame, "Ticker", milestones)
    ticker_history = [x for x in ticker_history if x.get("signal_count", 0) >= 2]

    payload: dict[str, Any] = {
        "expert": "siyoon",
        "evidence_type": "historical_range_validation",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "range_start": range_start,
        "range_end": range_end,
        "forward_bars": int(forward_bars),
        "candidate_signal_count": int(len(frame)),
        "usage_rule": (
            "사후 성과는 현재 신호 생성이나 원래 Score 계산에 사용하지 않고, "
            "현재 후보의 confidence/risk를 보조 검증하는 historical evidence로만 사용한다."
        ),
        "overall": _aggregate(frame, milestones),
        "by_status": _grouped(frame, "Status", milestones),
        "by_score_band": _grouped(frame, "Score_Band", milestones),
        "by_primary_signal": _grouped(frame, "Primary_Signal", milestones, limit=20),
        "ticker_history": ticker_history,
        "data_warnings": [
            "range 분석의 연속 일별 신호는 서로 독립된 거래 표본이 아닐 수 있으므로 signal_count를 독립 표본 수로 해석하지 않는다.",
            "각 D+N 통계는 해당 N거래일이 실제로 완료된 행만 사용한다.",
            "과거 결과가 좋더라도 현재 차트의 추격위험·지지 훼손·데이터 품질 문제를 무시하지 않는다.",
        ],
    }

    json_path = agent_dir / "range_summary.json"
    md_path = agent_dir / "range_summary.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(payload, md_path)
    return json_path, md_path


def _fmt(value: Any, pct: bool = False) -> str:
    if value is None:
        return "-"
    suffix = "%" if pct else ""
    return f"{value}{suffix}"


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# 시윤주식 과거 Range 검증 요약",
        "",
        f"- 기간: {payload['range_start']} ~ {payload['range_end']}",
        f"- 사후평가: D+1 ~ D+{payload['forward_bars']} 거래봉",
        f"- 후보 신호 수: {payload['candidate_signal_count']}",
        f"- 사용 원칙: {payload['usage_rule']}",
        "",
        "## 전체 성과",
        "",
    ]

    overall = payload.get("overall", {})
    for stat in overall.get("milestones", []):
        lines.append(
            f"- D+{stat['day']}: complete={stat['complete_count']}, "
            f"win={_fmt(None if stat['win_rate'] is None else round(stat['win_rate'] * 100, 1), True)}, "
            f"avg={_fmt(stat['avg_return_pct'], True)}, median={_fmt(stat['median_return_pct'], True)}, "
            f"MFE={_fmt(stat['avg_mfe_pct'], True)}, MAE={_fmt(stat['avg_mae_pct'], True)}"
        )

    lines.extend([
        f"- Upper before stop: {_fmt(None if overall.get('upper_before_stop_rate') is None else round(overall['upper_before_stop_rate'] * 100, 1), True)}",
        f"- Stop hit: {_fmt(None if overall.get('stop_hit_rate') is None else round(overall['stop_hit_rate'] * 100, 1), True)}",
        "",
        "## 해석 주의",
        "",
    ])
    lines.extend([f"- {x}" for x in payload.get("data_warnings", [])])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
