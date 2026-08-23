from __future__ import annotations
from typing import List
from ..models import Signal

def _sig(signals: List[Signal], category, name, score, direction, reason, **evidence):
    signals.append(Signal(name=name, score=score, category=category, direction=direction, reason=reason, evidence=evidence))

def build_signals(ctx: dict, weights: dict) -> list[Signal]:
    s: list[Signal] = []

    # 1) 추세
    t = ctx['trend']; maxw = weights['trend']
    trend_score = 0
    if t['alignment'] == 'bullish_alignment': trend_score += 9
    elif t['alignment'] == 'bearish_alignment': trend_score -= 9
    if t['above_life_ma']: trend_score += 4
    else: trend_score -= 2
    if t['above_long_ma']: trend_score += 3
    if t['up_structure']: trend_score += 5
    if t['down_structure']: trend_score -= 5
    if t['short_life_cross'] == 'golden_cross': trend_score += 4
    if t['short_life_cross'] == 'dead_cross': trend_score -= 4
    wt = ctx.get('weekly_trend')
    if wt:
        if wt['alignment'] == 'bullish_alignment': trend_score += 3
        elif wt['alignment'] == 'bearish_alignment': trend_score -= 3
    if t.get('overextended_life'): trend_score -= 2
    if t.get('overextended_long'): trend_score -= 2
    trend_score = max(-maxw, min(maxw, trend_score))
    _sig(s,'trend','추세·이평선',trend_score,'bullish' if trend_score>0 else 'bearish' if trend_score<0 else 'neutral',
         f"일봉배열={t['alignment']}, 주봉배열={wt['alignment'] if wt else '데이터부족'}, 20일선 위={t['above_life_ma']}, 상승구조={t['up_structure']}, 교차={t['short_life_cross']}, 20일 이격={t.get('life_gap_pct',0):.1%}")

    # 2) 가격 위치 / 지지·저항
    sr = ctx['sr']; br = ctx['breakout']; close=ctx['close']; loc=0
    ns=sr['nearest_support']; nr=sr['nearest_resistance']
    if ns and (close-ns)/close <= 0.035: loc += 5
    if br['retest_support_level']: loc += 6
    if br['breakout_level']: loc += 7
    if nr and (nr-close)/close <= 0.025 and not br['breakout_level']: loc -= 2
    if br['breakdown_level']: loc -= 8
    loc=max(-weights['location'],min(weights['location'],loc))
    _sig(s,'location','지지·저항 위치',loc,'bullish' if loc>0 else 'bearish' if loc<0 else 'neutral',
         f"최근 지지={ns}, 최근 저항={nr}, 돌파={br['breakout_level']}, 지지이탈={br['breakdown_level']}, 저항→지지={br['retest_support_level']}")

    # 3) 캔들
    c=ctx['candle']; cs=0; reasons=[]
    if c.get('morning_star_like'): cs += 5; reasons.append('모닝스타 유사')
    if c.get('evening_star_like'): cs -= 5; reasons.append('이브닝스타 유사')
    if c.get('long_lower_wick'): cs += 3; reasons.append('긴 아래꼬리')
    if c.get('long_upper_wick'): cs -= 3; reasons.append('긴 위꼬리')
    if c.get('three_bullish'): cs += 4; reasons.append('연속 3양봉')
    if c.get('three_bearish'): cs -= 4; reasons.append('연속 3음봉')
    pos = ctx.get('position_60d',0.5)
    if c.get('doji'):
        reasons.append('도지')
        if pos >= 0.80: cs -= 2; reasons.append('고점권 도지')
        elif pos <= 0.20: cs += 2; reasons.append('저점권 도지')
    if c.get('long_upper_wick') and pos >= 0.75: cs -= 1
    if c.get('long_lower_wick') and pos <= 0.25: cs += 1
    cs=max(-weights['candle'],min(weights['candle'],cs))
    _sig(s,'candle','캔들',cs,'bullish' if cs>0 else 'bearish' if cs<0 else 'neutral', ', '.join(reasons) or '특이 캔들 없음')

    # 4) 거래량
    v=ctx['volume']; vs=0; vr=[]
    if v['bullish_confirm']: vs += 6; vr.append('상승+거래량 확인')
    if v['bearish_confirm']: vs -= 6; vr.append('하락+거래량 확인')
    if v['distribution_hint']: vs -= 5; vr.append('고점 분배 가능성')
    if v['high_volume_stall']: vs -= 3; vr.append('고거래량 정체')
    if v['dry_volume'] and t['alignment']=='bullish_alignment': vs += 1; vr.append('상승추세 내 거래량 건조')
    vs=max(-weights['volume'],min(weights['volume'],vs))
    _sig(s,'volume','거래량 확인',vs,'bullish' if vs>0 else 'bearish' if vs<0 else 'neutral', ', '.join(vr) or '중립', relative_volume=round(v['relative_volume'],2))

    # 5) 구조
    ss=0; sr_reason=[]
    if br['breakout_level']: ss += 8; sr_reason.append('저항 돌파')
    if br['retest_support_level']: ss += 5; sr_reason.append('돌파 후 지지전환')
    if br['breakdown_level']: ss -= 9; sr_reason.append('지지선 이탈')
    if t['higher_lows']: ss += 3; sr_reason.append('저점 상승')
    if t['lower_highs']: ss -= 3; sr_reason.append('고점 하락')
    ss=max(-weights['structure'],min(weights['structure'],ss))
    _sig(s,'structure','시장 구조',ss,'bullish' if ss>0 else 'bearish' if ss<0 else 'neutral', ', '.join(sr_reason) or '뚜렷한 구조 신호 없음')

    # 6) 패턴
    p=ctx['patterns']; ps=0; pr=[]
    if p['double'].get('double_bottom'): ps += 4; pr.append('쌍바닥')
    if p['double'].get('double_top'): ps -= 4; pr.append('쌍봉')
    if p['cup'].get('cup_handle'): ps += 4; pr.append('컵앤핸들 유사')
    if p['hs'].get('inverse_head_shoulders'): ps += 4; pr.append('역헤드앤숄더 유사')
    if p['hs'].get('head_shoulders'): ps -= 4; pr.append('헤드앤숄더 유사')
    ps=max(-weights['pattern'],min(weights['pattern'],ps))
    _sig(s,'pattern','패턴',ps,'bullish' if ps>0 else 'bearish' if ps<0 else 'neutral', ', '.join(pr) or '뚜렷한 패턴 없음')

    # 7) 볼린저밴드
    b=ctx['bollinger']; bs=0; brr=[]
    if b['squeeze']: brr.append('스퀴즈')
    if b['upper_band_walk'] and t['alignment']=='bullish_alignment': bs += 6; brr.append('상단 밴드워킹')
    if b['lower_band_walk'] and t['alignment']=='bearish_alignment': bs -= 6; brr.append('하단 밴드워킹')
    if b['near_upper'] and t['alignment']!='bullish_alignment': bs -= 2; brr.append('비추세 상단 접근')
    if b['near_lower'] and t['alignment']!='bearish_alignment': bs += 2; brr.append('비추세 하단 접근')
    # 스퀴즈 자체는 방향점수를 주지 않는다: 강의 내용을 그대로 반영.
    bs=max(-weights['bollinger'],min(weights['bollinger'],bs))
    _sig(s,'bollinger','볼린저밴드',bs,'bullish' if bs>0 else 'bearish' if bs<0 else 'neutral', ', '.join(brr) or '중립')
    return s

def normalized_total(signals: list[Signal], weights: dict) -> float:
    raw = sum(s.score for s in signals)
    max_abs = sum(weights.values())
    # -max_abs~+max_abs 를 0~100으로 변환
    return round(50 + (raw/max_abs)*50, 2)
