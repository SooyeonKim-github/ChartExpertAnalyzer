from __future__ import annotations
from typing import Any


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, v)), 2)


def _grade(score: float) -> str:
    if score >= 80:
        return 'A+'
    if score >= 72:
        return 'A'
    if score >= 62:
        return 'B'
    if score >= 52:
        return 'C'
    if score >= 40:
        return 'D'
    return 'F'


def score_technical_quality(ctx: dict) -> tuple[float, dict[str, float], list[str], list[str]]:
    """종목 자체의 차트 품질을 평가한다.

    현재 하루의 매수 위치보다 느리게 변하는 추세/구조를 중심으로 본다.
    강의의 '정배열 + 고저점 상승 + 지지/저항 역할전환 + 여러 근거 중첩'을 정량화한 구현 규칙이다.
    """
    t = ctx['trend']
    wt = ctx.get('weekly_trend')
    br = ctx['breakout']
    p = ctx['patterns']
    b = ctx['bollinger']

    components: dict[str, float] = {}
    strengths: list[str] = []
    risks: list[str] = []

    # 1) 일봉 추세 0~30
    daily = 15.0
    if t['alignment'] == 'bullish_alignment':
        daily += 9; strengths.append('일봉 이동평균선 정배열')
    elif t['alignment'] == 'bearish_alignment':
        daily -= 11; risks.append('일봉 이동평균선 역배열')
    if t['above_life_ma']: daily += 3
    else: daily -= 3
    if t['above_long_ma']: daily += 3
    else: daily -= 4
    if t['ma_slopes'].get(20, 0) > 0: daily += 2
    elif t['ma_slopes'].get(20, 0) < 0: daily -= 2
    if t['ma_slopes'].get(60, 0) > 0: daily += 2
    elif t['ma_slopes'].get(60, 0) < 0: daily -= 2
    components['일봉 추세'] = _clamp(daily, 0, 30)

    # 2) 주봉 교차검증 0~15
    weekly = 7.5
    if wt:
        if wt['alignment'] == 'bullish_alignment':
            weekly += 5; strengths.append('주봉 정배열로 장기 추세 확인')
        elif wt['alignment'] == 'bearish_alignment':
            weekly -= 6; risks.append('주봉 역배열')
        if wt['above_life_ma']: weekly += 1.5
        else: weekly -= 1.5
        if wt['up_structure']: weekly += 1
        if wt['down_structure']: weekly -= 1
        if wt['alignment'] != t['alignment'] and wt['alignment'] != 'unknown':
            risks.append('일봉과 주봉 배열 불일치')
    components['주봉 교차검증'] = _clamp(weekly, 0, 15)

    # 3) 고점/저점 구조 0~25
    structure = 12.5
    if t['higher_highs']: structure += 5; strengths.append('고점 상승(Higher High)')
    if t['higher_lows']: structure += 6; strengths.append('저점 상승(Higher Low)')
    if t['up_structure']: structure += 3
    if t['lower_highs']: structure -= 5; risks.append('고점 하락(Lower High)')
    if t['lower_lows']: structure -= 6; risks.append('저점 하락(Lower Low)')
    if t['down_structure']: structure -= 3
    components['고저점 구조'] = _clamp(structure, 0, 25)

    # 4) 지지/저항 구조 0~20
    sr_score = 10.0
    if br['breakout_level']:
        sr_score += 4; strengths.append('최근 저항선 돌파')
    if br['retest_support_level']:
        sr_score += 6; strengths.append('돌파 저항이 지지로 전환')
    if br['breakdown_level']:
        sr_score -= 9; risks.append('주요 지지선 이탈')
    components['지지·저항 구조'] = _clamp(sr_score, 0, 20)

    # 5) 패턴/볼린저 추세 보조 0~10
    pattern = 5.0
    if p['double'].get('double_bottom'): pattern += 2; strengths.append('쌍바닥/W 구조')
    if p['cup'].get('cup_handle'): pattern += 2; strengths.append('컵앤핸들 유사 구조')
    if p['hs'].get('inverse_head_shoulders'): pattern += 2; strengths.append('역헤드앤숄더 유사 구조')
    if p['double'].get('double_top'): pattern -= 2; risks.append('쌍봉/더블탑 경계')
    if p['hs'].get('head_shoulders'): pattern -= 3; risks.append('헤드앤숄더 유사 구조')
    if b['upper_band_walk'] and t['alignment'] == 'bullish_alignment': pattern += 1; strengths.append('상승추세 상단 밴드워킹')
    if b['lower_band_walk'] and t['alignment'] == 'bearish_alignment': pattern -= 2; risks.append('하락추세 하단 밴드워킹')
    components['패턴·밴드 추세'] = _clamp(pattern, 0, 10)

    score = sum(components.values())
    return _clamp(score), components, strengths, risks


def score_entry_timing(ctx: dict, market_regime: str, cfg: dict) -> tuple[float, dict[str, float], list[str], list[str], str]:
    """지금 이 가격에서 신규 진입하기 좋은지를 평가한다."""
    t = ctx['trend']; sr = ctx['sr']; br = ctx['breakout']; c = ctx['candle']
    v = ctx['volume']; b = ctx['bollinger']; close = ctx['close']; pos = ctx['position_60d']
    recent5 = ctx.get('recent_return_5d', 0.0)
    components: dict[str, float] = {}
    strengths: list[str] = []
    risks: list[str] = []

    # 1) 가격 위치 0~30
    location = 15.0
    ns, nr = sr['nearest_support'], sr['nearest_resistance']
    if ns:
        support_gap = (close - ns) / close
        if 0 <= support_gap <= 0.025:
            location += 8; strengths.append('주요 지지선 2.5% 이내')
        elif 0 <= support_gap <= 0.05:
            location += 4; strengths.append('주요 지지선 근접')
    if br['retest_support_level']:
        location += 9; strengths.append('돌파 후 눌림목 지지 확인')
    if br['breakout_level']:
        location += 5; strengths.append('신규 저항 돌파')
    if nr and nr > close:
        resistance_gap = (nr-close)/close
        if resistance_gap <= 0.02 and not br['breakout_level']:
            location -= 7; risks.append('바로 위 강한 저항 접근')
    if br['breakdown_level']:
        location -= 12; risks.append('지지 붕괴 직후')
    components['가격 위치'] = _clamp(location, 0, 30)

    # 2) 이평선/추격 위험 0~25
    ma_timing = 13.0
    gap = t.get('life_gap_pct', 0.0)
    if gap == gap:  # NaN 방지
        if -0.02 <= gap <= 0.04:
            ma_timing += 8; strengths.append('20일선과 이격이 안정적')
        elif 0.04 < gap <= 0.08:
            ma_timing += 3
        elif 0.08 < gap < cfg['moving_average']['distance_warn_life_pct']:
            ma_timing -= 3; risks.append('20일선 이격 확대')
        elif gap >= cfg['moving_average']['distance_warn_life_pct']:
            ma_timing -= 10; risks.append('20일선 과도 이격으로 추격 위험')
        elif gap < -0.05:
            ma_timing -= 5; risks.append('20일선 아래 약세 위치')
    if t['short_life_cross'] == 'golden_cross':
        ma_timing += 5; strengths.append('5-20 골든크로스 발생')
    elif t['short_life_cross'] == 'dead_cross':
        ma_timing -= 8; risks.append('5-20 데드크로스 발생')
    if pos >= 0.90 and recent5 >= cfg['timing']['chase_recent_5d_return']:
        ma_timing -= 6; risks.append('60일 고점권 단기 급등으로 추격매수 위험')
    components['이평선·추격 위험'] = _clamp(ma_timing, 0, 25)

    # 3) 캔들/거래량 0~25
    cv = 12.5
    if c.get('morning_star_like'):
        cv += 5; strengths.append('모닝스타 유사 반전')
    if c.get('long_lower_wick') and pos <= 0.35:
        cv += 4; strengths.append('저점권 긴 아래꼬리')
    if c.get('three_bullish'):
        cv += 3; strengths.append('3연속 양봉')
    if c.get('evening_star_like'):
        cv -= 6; risks.append('이브닝스타 유사')
    if c.get('long_upper_wick') and pos >= 0.70:
        cv -= 5; risks.append('고점권 긴 위꼬리')
    if c.get('three_bearish'):
        cv -= 4; risks.append('3연속 음봉')
    if v['bullish_confirm']:
        cv += 6; strengths.append(f"상승 거래량 확인({v['relative_volume']:.2f}배)")
    if v['bearish_confirm']:
        cv -= 7; risks.append(f"하락 거래량 확인({v['relative_volume']:.2f}배)")
    if v['distribution_hint']:
        cv -= 8; risks.append('고점 거래량·위꼬리 분배 가능성')
    if v['high_volume_stall']:
        cv -= 4; risks.append('고거래량에도 가격 정체')
    components['캔들·거래량'] = _clamp(cv, 0, 25)

    # 4) 볼린저/시장 상태 0~20
    bm = 10.0
    if b['squeeze']:
        strengths.append('볼린저 스퀴즈: 방향 확인 대기')
    if b['upper_band_walk'] and t['alignment'] == 'bullish_alignment':
        bm += 4; strengths.append('정배열 상단 밴드워킹')
    if b['lower_band_walk'] and t['alignment'] == 'bearish_alignment':
        bm -= 7; risks.append('역배열 하단 밴드워킹')
    if b['near_upper'] and (t.get('overextended_life') or recent5 >= cfg['timing']['chase_recent_5d_return']):
        bm -= 4; risks.append('과열 상태에서 볼린저 상단 접근')
    if market_regime == 'uptrend': bm += 4; strengths.append('시장 상승추세')
    elif market_regime == 'downtrend': bm -= 6; risks.append('시장 하락추세')
    elif market_regime == 'volatile': bm -= 4; risks.append('변동성 장세')
    components['볼린저·시장'] = _clamp(bm, 0, 20)

    score = _clamp(sum(components.values()))

    # 추격위험 단계
    chase_points = 0
    if t.get('overextended_life'): chase_points += 2
    if pos >= 0.90: chase_points += 1
    if recent5 >= cfg['timing']['chase_recent_5d_return']: chase_points += 2
    if b['near_upper']: chase_points += 1
    if c.get('long_upper_wick') and pos >= 0.70: chase_points += 1
    chase = '높음' if chase_points >= 4 else '보통' if chase_points >= 2 else '낮음'
    return score, components, strengths, risks, chase


def score_risk(ctx: dict, market_regime: str) -> tuple[float, list[str]]:
    """높을수록 신규 진입 위험이 큰 0~100 위험 점수."""
    t=ctx['trend']; wt=ctx.get('weekly_trend'); br=ctx['breakout']; v=ctx['volume']; c=ctx['candle']; b=ctx['bollinger']
    pos=ctx['position_60d']; recent5=ctx.get('recent_return_5d',0.0)
    score=18.0; reasons=[]
    if t['alignment']=='bearish_alignment': score += 20; reasons.append('일봉 역배열')
    if wt and wt['alignment']=='bearish_alignment': score += 10; reasons.append('주봉 역배열')
    if wt and wt['alignment'] != t['alignment'] and wt['alignment']!='unknown': score += 6; reasons.append('일봉/주봉 불일치')
    if br['breakdown_level']: score += 18; reasons.append('지지선 이탈')
    if t['down_structure']: score += 14; reasons.append('고점·저점 동반 하락')
    if v['distribution_hint']: score += 16; reasons.append('분배 가능성')
    if v['high_volume_stall']: score += 8; reasons.append('고거래량 정체')
    if t.get('overextended_life'): score += 12; reasons.append('20일선 과도 이격')
    if c.get('long_upper_wick') and pos >= .75: score += 8; reasons.append('고점권 긴 위꼬리')
    if b['lower_band_walk'] and t['alignment']=='bearish_alignment': score += 10; reasons.append('하단 밴드워킹')
    if recent5 >= 0.10 and pos >= .90: score += 8; reasons.append('단기 급등 후 고점권')
    if market_regime=='downtrend': score += 10; reasons.append('시장 하락추세')
    elif market_regime=='volatile': score += 6; reasons.append('시장 변동성 확대')
    if br['retest_support_level'] and t['alignment']=='bullish_alignment': score -= 8
    if t['up_structure'] and t['alignment']=='bullish_alignment': score -= 5
    return _clamp(score), reasons


def build_decision(ctx: dict, market_regime: str, cfg: dict) -> dict[str, Any]:
    tech, tech_comp, tech_strengths, tech_risks = score_technical_quality(ctx)
    timing, timing_comp, timing_strengths, timing_risks, chase = score_entry_timing(ctx, market_regime, cfg)
    risk, risk_reasons = score_risk(ctx, market_regime)

    # 위험 점수가 50을 넘는 부분만 최대 10점까지 선택점수에 패널티.
    risk_penalty = min(10.0, max(0.0, risk-50.0)*0.20)
    selection = _clamp(tech*0.55 + timing*0.45 - risk_penalty)

    sr=ctx['sr']; br=ctx['breakout']
    close=ctx['close']; nr=sr['nearest_resistance']
    near_resistance = bool(nr and nr > close and (nr-close)/close <= 0.025 and not br['breakout_level'])

    if tech < 45 or risk >= 78:
        entry_status = '매수 회피 · 구조 회복 확인'
    elif tech >= 75 and timing >= 75 and risk < 60 and chase != '높음':
        entry_status = '분할진입 우수'
    elif tech >= 75 and chase == '높음':
        entry_status = '좋은 종목 · 눌림목 대기'
    elif tech >= 72 and near_resistance:
        entry_status = '좋은 종목 · 저항 돌파 확인 대기'
    elif tech >= 72 and timing >= 60:
        entry_status = '좋은 종목 · 관심 진입'
    elif tech >= 62 and timing >= 72 and risk < 60:
        entry_status = '구조 개선 중 · 소액 정찰 가능'
    elif tech >= 62:
        entry_status = '관심 종목 · 타이밍 확인 대기'
    elif timing >= 70 and risk < 55:
        entry_status = '단기 반전 후보 · 추세 확인 필요'
    else:
        entry_status = '관찰'

    strengths=[]
    for x in tech_strengths + timing_strengths:
        if x not in strengths: strengths.append(x)
    risks=[]
    for x in tech_risks + timing_risks + risk_reasons:
        if x not in risks: risks.append(x)

    return {
        'technical_score': tech,
        'technical_grade': _grade(tech),
        'technical_components': tech_comp,
        'timing_score': timing,
        'timing_grade': _grade(timing),
        'timing_components': timing_comp,
        'risk_score': risk,
        'risk_level': '높음' if risk >= 65 else '보통' if risk >= 40 else '낮음',
        'chase_risk': chase,
        'selection_score': selection,
        'selection_grade': _grade(selection),
        'entry_status': entry_status,
        'strengths': strengths[:10],
        'risks': risks[:10],
    }
