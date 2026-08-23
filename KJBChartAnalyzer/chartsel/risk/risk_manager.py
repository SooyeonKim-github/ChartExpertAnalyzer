from __future__ import annotations

def initial_stop(close: float, support: float | None, risk_cfg: dict) -> float:
    pct_stop = close * (1-risk_cfg['initial_stop_pct'])
    max_stop = close * (1-risk_cfg['max_stop_pct'])
    if support is None:
        return round(max(pct_stop, max_stop), 4)
    structural = support * 0.985
    return round(max(max_stop, min(pct_stop, structural)), 4)

def trailing_stop(highest_close_since_entry: float, risk_cfg: dict) -> float:
    return round(highest_close_since_entry * (1-risk_cfg['trailing_stop_pct']), 4)

def pyramiding_plan(risk_cfg: dict) -> list[dict]:
    steps = [{'step':1, 'fraction':risk_cfg['initial_entry_pct'], 'trigger':'초기 구조 확인'}]
    triggers = ['골든크로스/정배열 강화', '저항·넥라인 돌파', '눌림목 지지 확인', '재돌파/추세 지속 확인']
    for i,p in enumerate(risk_cfg['add_entry_pcts'], start=2):
        steps.append({'step':i, 'fraction':p, 'trigger':triggers[min(i-2, len(triggers)-1)]})
    return steps

def contextual_entry_plan(ctx: dict, decision: dict, risk_cfg: dict, market_regime: str) -> list[dict]:
    """강의의 피라미딩 예시를 현재 차트 신호와 연결한 진입 계획."""
    fractions = [risk_cfg['initial_entry_pct'], *risk_cfg['add_entry_pcts']]
    t=ctx['trend']; br=ctx['breakout']; v=ctx['volume']; b=ctx['bollinger']
    conditions = [
        (decision['technical_score'] >= 62 and decision['timing_score'] >= 60 and decision['chase_risk'] != '높음',
         '초기 구조·타이밍 확인'),
        (t['short_life_cross']=='golden_cross' or (t['alignment']=='bullish_alignment' and t['above_life_ma']),
         '골든크로스 또는 정배열 강화'),
        (bool(br['breakout_level']) and v['bullish_confirm'],
         '저항·넥라인 거래량 돌파'),
        (bool(br['retest_support_level']),
         '돌파 후 눌림목 지지 확인'),
        ((t['up_structure'] and t['alignment']=='bullish_alignment') or (b['upper_band_walk'] and t['alignment']=='bullish_alignment'),
         '재돌파/상승추세 지속 확인'),
    ]
    plan=[]
    for i,(fraction,(ok,trigger)) in enumerate(zip(fractions,conditions), start=1):
        status='충족' if ok else '대기'
        if i == 1 and market_regime != 'uptrend':
            status='조건부' if ok else '대기'
        if decision['risk_score'] >= 65:
            status='보류' if status=='충족' else status
        plan.append({'step':i,'fraction':fraction,'trigger':trigger,'status':status})
    return plan
