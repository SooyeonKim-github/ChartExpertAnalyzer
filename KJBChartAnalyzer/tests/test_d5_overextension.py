from chartsel.analysis.overextension import evaluate_overextension
from chartsel.selection.confirmation import classify_confirmation_values


def _cfg():
    return {
        'overextension': {
            'enabled': True,
            'max_total_penalty': 20,
            'selection': {'threshold': 85, 'step': 5, 'penalty_per_step': 1.5, 'cap': 4.5},
            'leader': {'threshold': 85, 'step': 5, 'penalty_per_step': 2.0, 'cap': 6.0},
            'relative_strength': {'threshold': 90, 'step': 5, 'penalty_per_step': 2.0, 'cap': 6.0},
            'chase_risk': {'medium_penalty': 0.0, 'high_penalty': 4.0},
        },
        'confirmation_v1': {
            'use_d5_score': True,
            'selection_min': 70,
            'selection_max': 100,
            'timing_min': 72,
            'timing_max': 100,
            'leader_min': 70,
            'leader_max': 100,
            'relative_strength_min': 40,
            'relative_strength_max': 100,
            'risk_max_exclusive': 60,
            'reject_high_chase': True,
            'watch_selection_min': 62,
            'watch_technical_min': 62,
            'watch_risk_max_exclusive': 65,
        },
    }


def test_no_penalty_inside_normal_zone():
    out = evaluate_overextension(
        selection_score=80,
        leader_score=80,
        relative_strength_score=85,
        chase_risk='낮음',
        cfg=_cfg()['overextension'],
    )
    assert out['penalty'] == 0
    assert out['d5_score'] == 80


def test_extreme_strength_is_penalized():
    out = evaluate_overextension(
        selection_score=95,
        leader_score=95,
        relative_strength_score=98,
        chase_risk='낮음',
        cfg=_cfg()['overextension'],
    )
    assert out['penalty'] > 0
    assert out['d5_score'] < 95
    assert out['components']['leader'] > 0
    assert out['components']['relative_strength'] > 0


def test_confirmation_recomputes_same_d5_score_when_column_missing():
    cfg = _cfg()
    status = classify_confirmation_values(
        selection_score=74,
        technical_score=75,
        timing_score=75,
        risk_score=40,
        leader_score=95,
        relative_strength_score=98,
        chase_risk='낮음',
        cfg=cfg,
    )
    assert status == 'WATCH'


def test_high_chase_cannot_be_confirmed():
    cfg = _cfg()
    status = classify_confirmation_values(
        selection_score=85,
        technical_score=80,
        timing_score=80,
        risk_score=40,
        leader_score=80,
        relative_strength_score=80,
        chase_risk='높음',
        cfg=cfg,
    )
    assert status != 'CONFIRMED'
