from __future__ import annotations
import pandas as pd
from ..models import AnalysisResult
from ..indicators.moving_average import add_moving_averages
from ..indicators.volume import add_volume_features, volume_context
from ..indicators.candlestick import detect_candles
from ..indicators.bollinger import add_bollinger, bollinger_context
from ..structure.pivots import find_pivots
from ..structure.support_resistance import support_resistance, breakout_retest_state
from ..structure.trend import trend_context
from ..patterns.double_patterns import detect_double_bottom_top
from ..patterns.cup_handle import detect_cup_handle
from ..patterns.head_shoulders import detect_head_shoulders
from .market_regime import classify_market_regime
from .scoring import build_signals, normalized_total
from .decision import build_decision
from .relative_strength import relative_strength_context, leader_score
from ..risk.risk_manager import initial_stop, trailing_stop, contextual_entry_plan


def _to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        'Open': df['Open'].resample('W-FRI').first(),
        'High': df['High'].resample('W-FRI').max(),
        'Low': df['Low'].resample('W-FRI').min(),
        'Close': df['Close'].resample('W-FRI').last(),
        'Volume': df['Volume'].resample('W-FRI').sum(),
    }).dropna()

class ChartAnalyzer:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        x = add_moving_averages(df, self.cfg['moving_average'])
        x = add_volume_features(x, self.cfg['volume'])
        x = add_bollinger(x, self.cfg['bollinger'])
        x = find_pivots(x, self.cfg['structure']['pivot_left'], self.cfg['structure']['pivot_right'])
        return x

    def analyze(self, ticker: str, df: pd.DataFrame, market_df: pd.DataFrame | None = None) -> AnalysisResult:
        x = self.prepare(df)
        min_len = max(self.cfg['moving_average']['long']+10, 140)
        if len(x) < min_len:
            raise ValueError(f'{ticker}: 최소 {min_len}개 일봉이 필요합니다.')
        sr = support_resistance(x, self.cfg['structure'])
        br = breakout_retest_state(x, sr, self.cfg['structure'])
        weekly_raw = _to_weekly(df)
        weekly_trend = None
        if len(weekly_raw) >= 130:
            weekly_x = self.prepare(weekly_raw)
            weekly_trend = trend_context(weekly_x, self.cfg['moving_average'])
        pos_window = x['Close'].tail(60)
        pos60 = 0.5 if pos_window.max() == pos_window.min() else float((x['Close'].iloc[-1]-pos_window.min())/(pos_window.max()-pos_window.min()))
        ctx = {
            'close': float(x['Close'].iloc[-1]),
            'recent_return_5d': float(x['Close'].iloc[-1] / x['Close'].iloc[-6] - 1) if len(x) >= 6 else 0.0,
            'recent_return_20d': float(x['Close'].iloc[-1] / x['Close'].iloc[-21] - 1) if len(x) >= 21 else 0.0,
            'trend': trend_context(x, self.cfg['moving_average']),
            'weekly_trend': weekly_trend,
            'position_60d': pos60,
            'sr': sr,
            'breakout': br,
            'candle': detect_candles(x, self.cfg['candlestick']),
            'volume': volume_context(x, self.cfg['volume']),
            'bollinger': bollinger_context(x, self.cfg['bollinger']),
            'patterns': {
                'double': detect_double_bottom_top(x, self.cfg['structure']),
                'cup': detect_cup_handle(x, self.cfg['structure']),
                'hs': detect_head_shoulders(x, self.cfg['structure']),
            }
        }
        regime_df = self.prepare(market_df) if market_df is not None else x
        regime = classify_market_regime(regime_df, self.cfg['moving_average'])
        signals = build_signals(ctx, self.cfg['weights'])
        confluence_score = normalized_total(signals, self.cfg['weights'])
        decision = build_decision(ctx, regime, self.cfg)
        rs = relative_strength_context(x, regime_df if market_df is not None else None)
        lead_score, rs_weight = leader_score(
            decision['selection_score'], rs['score'], regime, self.cfg.get('relative_strength', {})
        )
        score = decision['selection_score']
        grade = decision['selection_grade']
        action = decision['entry_status']

        # 강의의 피라미딩은 상승 추세장에서만 권장한다.
        if self.cfg['selection']['require_market_uptrend_for_pyramiding'] and regime != 'uptrend' and action in ('분할진입 우수','좋은 종목 · 관심 진입'):
            action = '조건부 관심 · 시장 추세 확인 필요'

        support = sr['nearest_support']
        stop = initial_stop(ctx['close'], support, self.cfg['risk'])
        highest = float(x['Close'].tail(60).max())
        trail = trailing_stop(highest, self.cfg['risk'])
        notes = []
        if ctx['bollinger']['squeeze']:
            notes.append('볼린저 스퀴즈는 방향 신호가 아니므로 돌파 방향 확인이 필요합니다.')
        if ctx['volume']['distribution_hint']:
            notes.append('고점권 거래량·위꼬리 조합은 분배 가능성을 점검합니다.')
        if ctx['trend']['alignment'] == 'bearish_alignment':
            notes.append('역배열은 싸 보이더라도 추세 회복 확인 전 선매수를 제한합니다.')
        if ctx['trend']['overextended_life'] or ctx['trend']['overextended_long']:
            notes.append('이평선과 이격이 크게 벌어진 상태입니다. 강한 추세라도 단기 되돌림 위험을 함께 봅니다.')
        if weekly_trend and weekly_trend['alignment'] != ctx['trend']['alignment']:
            notes.append('일봉과 주봉의 이동평균 배열이 다릅니다. 시간대 교차검증이 필요합니다.')
        if br['breakout_level'] and ctx['volume']['bullish_confirm']:
            notes.append('저항 돌파와 거래량 확인이 동시에 발생했습니다.')
        if rs['available'] and rs['score'] >= 70:
            notes.append('지수 대비 상대강도가 높습니다. 하락 방어력·초과수익·회복 우위를 함께 확인했습니다.')
        elif rs['available'] and rs['score'] < 40:
            notes.append('종목 자체 차트와 별개로 지수 대비 상대강도는 약합니다.')
        entry_plan = contextual_entry_plan(ctx, decision, self.cfg['risk'], regime)
        return AnalysisResult(
            ticker=ticker,
            asof=str(x.index[-1].date()),
            close=ctx['close'],
            total_score=score,
            grade=grade,
            action=action,
            market_regime=regime,
            confluence_score=confluence_score,
            relative_strength_score=rs['score'],
            relative_strength_grade=rs['grade'],
            leader_score=lead_score,
            relative_strength_weight=rs_weight,
            relative_strength_metrics={k:v for k,v in rs.items() if k not in ('score','grade')},
            technical_score=decision['technical_score'],
            technical_grade=decision['technical_grade'],
            timing_score=decision['timing_score'],
            timing_grade=decision['timing_grade'],
            risk_score=decision['risk_score'],
            risk_level=decision['risk_level'],
            chase_risk=decision['chase_risk'],
            entry_status=decision['entry_status'],
            technical_components=decision['technical_components'],
            timing_components=decision['timing_components'],
            strengths=decision['strengths'],
            risks=decision['risks'],
            signals=signals,
            support_levels=sr['supports'][-5:],
            resistance_levels=sr['resistances'][-5:],
            stop_price=stop,
            trailing_stop_price=trail,
            entry_plan=entry_plan,
            notes=notes,
        )
