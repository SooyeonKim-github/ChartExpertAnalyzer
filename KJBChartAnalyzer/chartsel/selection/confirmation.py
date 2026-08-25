from __future__ import annotations


def classify_confirmation_v1(result, cfg: dict) -> str:
    """백테스트로 검증 중인 KJB CONFIRMED V1 상태를 반환한다.

    일일 Screen과 Range Backtest가 같은 함수를 사용해야 임계값/판정 차이가 생기지 않는다.

    CONFIRMED
    - Selection >= 70
    - Timing >= 72
    - Leader >= 70
    - Relative Strength >= 40
    - Risk < 60
    - Chase Risk != 높음

    WATCH
    - Selection >= 62
    - Technical >= 62
    - Risk < 65

    나머지는 REJECTED.
    실제 임계값은 config/default.yaml의 confirmation_v1에서 조정한다.
    """
    c = cfg.get('confirmation_v1', {}) or {}

    confirmed = (
        result.total_score >= float(c.get('selection_min', 70.0))
        and result.timing_score >= float(c.get('timing_min', 72.0))
        and result.leader_score >= float(c.get('leader_min', 70.0))
        and result.relative_strength_score >= float(c.get('relative_strength_min', 40.0))
        and result.risk_score < float(c.get('risk_max_exclusive', 60.0))
        and (
            not bool(c.get('reject_high_chase', True))
            or str(result.chase_risk) != '높음'
        )
    )
    if confirmed:
        return 'CONFIRMED'

    watch = (
        result.total_score >= float(c.get('watch_selection_min', 62.0))
        and result.technical_score >= float(c.get('watch_technical_min', 62.0))
        and result.risk_score < float(c.get('watch_risk_max_exclusive', 65.0))
    )
    return 'WATCH' if watch else 'REJECTED'
