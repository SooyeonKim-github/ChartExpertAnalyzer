from __future__ import annotations

from ..analysis.overextension import evaluate_overextension


def classify_confirmation_values(
    *,
    selection_score: float,
    technical_score: float,
    timing_score: float,
    risk_score: float,
    leader_score: float,
    relative_strength_score: float,
    chase_risk: str,
    cfg: dict,
    d5_score: float | None = None,
) -> str:
    """KJB CONFIRMED/WATCH/REJECTED를 공통 판정한다.

    use_d5_score=true이면 CONFIRMED의 Selection threshold에만 D+5 조정점수를
    적용한다. 과열 종목은 CONFIRMED에서 WATCH로 내려갈 수 있지만, 페널티 하나로
    기존 WATCH가 REJECTED까지 밀리는 것은 방지한다.
    """
    c = cfg.get('confirmation_v1', {}) or {}
    use_d5_score = bool(c.get('use_d5_score', False))

    raw_selection = float(selection_score)
    confirmed_selection = raw_selection
    if use_d5_score:
        if d5_score is None:
            over = evaluate_overextension(
                selection_score=selection_score,
                leader_score=leader_score,
                relative_strength_score=relative_strength_score,
                chase_risk=chase_risk,
                cfg=cfg.get('overextension', {}),
            )
            confirmed_selection = float(over['d5_score'])
        else:
            confirmed_selection = float(d5_score)

    confirmed = (
        confirmed_selection >= float(c.get('selection_min', 70.0))
        and confirmed_selection <= float(c.get('selection_max', 100.0))
        and float(timing_score) >= float(c.get('timing_min', 72.0))
        and float(timing_score) <= float(c.get('timing_max', 100.0))
        and float(leader_score) >= float(c.get('leader_min', 70.0))
        and float(leader_score) <= float(c.get('leader_max', 100.0))
        and float(relative_strength_score) >= float(c.get('relative_strength_min', 40.0))
        and float(relative_strength_score) <= float(c.get('relative_strength_max', 100.0))
        and float(risk_score) < float(c.get('risk_max_exclusive', 60.0))
        and (
            not bool(c.get('reject_high_chase', True))
            or str(chase_risk) != '높음'
        )
    )
    if confirmed:
        return 'CONFIRMED'

    watch = (
        raw_selection >= float(c.get('watch_selection_min', 62.0))
        and float(technical_score) >= float(c.get('watch_technical_min', 62.0))
        and float(risk_score) < float(c.get('watch_risk_max_exclusive', 65.0))
    )
    return 'WATCH' if watch else 'REJECTED'


def classify_confirmation_v1(result, cfg: dict) -> str:
    """AnalysisResult를 KJB CONFIRMED/WATCH/REJECTED로 판정한다."""
    return classify_confirmation_values(
        selection_score=result.total_score,
        technical_score=result.technical_score,
        timing_score=result.timing_score,
        risk_score=result.risk_score,
        leader_score=result.leader_score,
        relative_strength_score=result.relative_strength_score,
        chase_risk=result.chase_risk,
        d5_score=getattr(result, 'd5_score', None),
        cfg=cfg,
    )
