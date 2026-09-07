from __future__ import annotations

import math
from typing import Any


def _finite(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _scaled_penalty(value: Any, cfg: dict) -> float:
    x = _finite(value)
    if x is None:
        return 0.0
    threshold = float(cfg.get('threshold', 100.0))
    if x <= threshold:
        return 0.0
    step = max(float(cfg.get('step', 5.0)), 1e-9)
    points_per_step = float(cfg.get('penalty_per_step', 1.0))
    cap = max(float(cfg.get('cap', 100.0)), 0.0)
    return min(cap, max(0.0, (x - threshold) / step * points_per_step))


def grade_from_score(score: float) -> str:
    x = float(score)
    if x >= 80:
        return 'A+'
    if x >= 72:
        return 'A'
    if x >= 62:
        return 'B'
    if x >= 52:
        return 'C'
    if x >= 40:
        return 'D'
    return 'F'


def evaluate_overextension(
    *,
    selection_score: float,
    leader_score: float,
    relative_strength_score: float,
    chase_risk: str,
    cfg: dict | None,
) -> dict:
    """KJB D+5용 과열 페널티를 계산한다.

    첫 버전은 Range 데이터에서 실제로 역전 현상이 확인된 값만 사용한다.
    - Selection 85+ 영역
    - Leader 85+ 영역
    - Relative Strength 90+ 영역
    - 높은 chase risk

    가격 이격/최근 급등률은 이후 optimizer에서 추가 검증할 수 있도록 별도 확장한다.
    기존 Selection Score는 보존하고 d5_score만 감점한다.
    """
    c = cfg or {}
    enabled = bool(c.get('enabled', True))
    raw = max(0.0, min(100.0, float(selection_score)))
    if not enabled:
        return {
            'd5_score': round(raw, 2),
            'd5_grade': grade_from_score(raw),
            'penalty': 0.0,
            'components': {
                'selection': 0.0,
                'leader': 0.0,
                'relative_strength': 0.0,
                'chase': 0.0,
            },
        }

    components = {
        'selection': _scaled_penalty(selection_score, c.get('selection', {})),
        'leader': _scaled_penalty(leader_score, c.get('leader', {})),
        'relative_strength': _scaled_penalty(relative_strength_score, c.get('relative_strength', {})),
        'chase': 0.0,
    }

    chase_cfg = c.get('chase_risk', {}) or {}
    risk = str(chase_risk or '').strip()
    if risk == '높음':
        components['chase'] = float(chase_cfg.get('high_penalty', 4.0))
    elif risk == '보통':
        components['chase'] = float(chase_cfg.get('medium_penalty', 0.0))

    max_total = max(float(c.get('max_total_penalty', 20.0)), 0.0)
    penalty = min(max_total, sum(max(0.0, float(v)) for v in components.values()))
    d5_score = max(0.0, min(100.0, raw - penalty))

    return {
        'd5_score': round(d5_score, 2),
        'd5_grade': grade_from_score(d5_score),
        'penalty': round(penalty, 2),
        'components': {k: round(float(v), 2) for k, v in components.items()},
    }
