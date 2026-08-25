from __future__ import annotations


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
) -> str:
    """KJB CONFIRMED V1을 숫자 필드만으로 판정한다.

    일일 Screen과 Range Backtest가 이 함수를 공유해 동일한 기준을 사용한다.
    실제 임계값은 config/default.yaml의 confirmation_v1에서 조정한다.
    """
    c = cfg.get('confirmation_v1', {}) or {}

    confirmed = (
        float(selection_score) >= float(c.get('selection_min', 70.0))
        and float(timing_score) >= float(c.get('timing_min', 72.0))
        and float(leader_score) >= float(c.get('leader_min', 70.0))
        and float(relative_strength_score) >= float(c.get('relative_strength_min', 40.0))
        and float(risk_score) < float(c.get('risk_max_exclusive', 60.0))
        and (
            not bool(c.get('reject_high_chase', True))
            or str(chase_risk) != '높음'
        )
    )
    if confirmed:
        return 'CONFIRMED'

    watch = (
        float(selection_score) >= float(c.get('watch_selection_min', 62.0))
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
        cfg=cfg,
    )
