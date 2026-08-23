from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def _window_return(s: pd.Series, bars: int) -> float:
    x = s.dropna()
    if len(x) <= bars:
        return np.nan
    prev = float(x.iloc[-bars - 1])
    cur = float(x.iloc[-1])
    if prev == 0:
        return np.nan
    return cur / prev - 1.0


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


def relative_strength_context(stock_df: pd.DataFrame, market_df: pd.DataFrame | None) -> dict[str, Any]:
    """종목이 벤치마크보다 얼마나 강한지 0~100으로 정량화한다.

    강의의 핵심인
    - 지수 하락 때 덜 빠지는가
    - 지수보다 빠르게 회복하는가
    - 최근 20/60거래일 누적수익률이 지수를 앞서는가
    를 미래 데이터 없이 현재 시점까지의 데이터만 사용해 계산한다.

    market_df가 없거나 정렬 가능한 데이터가 부족하면 중립(50점)을 반환한다.
    """
    neutral = {
        'score': 50.0,
        'grade': 'C',
        'available': False,
        'relative_return_5d': np.nan,
        'relative_return_20d': np.nan,
        'relative_return_60d': np.nan,
        'down_day_hit_rate_20d': np.nan,
        'down_day_avg_excess_20d': np.nan,
        'drawdown_advantage_60d': np.nan,
        'rebound_advantage_60d': np.nan,
        'components': {},
    }
    if market_df is None or stock_df is None or stock_df.empty or market_df.empty:
        return neutral

    s = stock_df[['Close']].rename(columns={'Close': 'stock'}).copy()
    m = market_df[['Close']].rename(columns={'Close': 'market'}).copy()
    s.index = pd.to_datetime(s.index).normalize()
    m.index = pd.to_datetime(m.index).normalize()
    x = s.join(m, how='inner').dropna().sort_index()
    x = x[~x.index.duplicated(keep='last')]
    if len(x) < 22:
        return neutral

    r5_s = _window_return(x['stock'], 5)
    r5_m = _window_return(x['market'], 5)
    r20_s = _window_return(x['stock'], 20)
    r20_m = _window_return(x['market'], 20)
    r60_s = _window_return(x['stock'], 60)
    r60_m = _window_return(x['market'], 60)

    rel5 = r5_s - r5_m if np.isfinite(r5_s) and np.isfinite(r5_m) else np.nan
    rel20 = r20_s - r20_m if np.isfinite(r20_s) and np.isfinite(r20_m) else np.nan
    rel60 = r60_s - r60_m if np.isfinite(r60_s) and np.isfinite(r60_m) else np.nan

    daily = x.pct_change().dropna().tail(20)
    down = daily[daily['market'] < 0]
    if len(down) >= 3:
        down_excess = down['stock'] - down['market']
        down_hit = float((down['stock'] > down['market']).mean())
        down_avg_excess = float(down_excess.mean())
    else:
        down_hit = np.nan
        down_avg_excess = np.nan

    x60 = x.tail(61)
    if len(x60) >= 20:
        stock_dd = float(x60['stock'].iloc[-1] / x60['stock'].max() - 1.0)
        market_dd = float(x60['market'].iloc[-1] / x60['market'].max() - 1.0)
        dd_adv = stock_dd - market_dd  # 양수면 지수보다 덜 빠진 상태

        stock_rebound = float(x60['stock'].iloc[-1] / x60['stock'].min() - 1.0)
        market_rebound = float(x60['market'].iloc[-1] / x60['market'].min() - 1.0)
        rebound_adv = stock_rebound - market_rebound
    else:
        dd_adv = np.nan
        rebound_adv = np.nan

    # 절대적인 예측점수라기보다 '지수 대비 강도'를 50점 중립 기준으로 표현한다.
    # 과적합을 피하기 위해 각 항목의 영향은 상한을 둔다.
    components: dict[str, float] = {}
    components['5일 초과수익'] = 0.0 if not np.isfinite(rel5) else _clamp(rel5 / 0.05 * 7.5, -7.5, 7.5)
    components['20일 초과수익'] = 0.0 if not np.isfinite(rel20) else _clamp(rel20 / 0.10 * 15.0, -15.0, 15.0)
    components['60일 초과수익'] = 0.0 if not np.isfinite(rel60) else _clamp(rel60 / 0.20 * 12.5, -12.5, 12.5)
    components['하락일 방어 승률'] = 0.0 if not np.isfinite(down_hit) else _clamp((down_hit - 0.5) * 20.0, -10.0, 10.0)
    components['하락일 평균 초과수익'] = 0.0 if not np.isfinite(down_avg_excess) else _clamp(down_avg_excess / 0.01 * 7.5, -7.5, 7.5)
    components['60일 낙폭 우위'] = 0.0 if not np.isfinite(dd_adv) else _clamp(dd_adv / 0.10 * 10.0, -10.0, 10.0)
    components['60일 회복 우위'] = 0.0 if not np.isfinite(rebound_adv) else _clamp(rebound_adv / 0.20 * 7.5, -7.5, 7.5)

    score = round(_clamp(50.0 + sum(components.values()), 0.0, 100.0), 2)
    return {
        'score': score,
        'grade': _grade(score),
        'available': True,
        'relative_return_5d': rel5,
        'relative_return_20d': rel20,
        'relative_return_60d': rel60,
        'down_day_hit_rate_20d': down_hit,
        'down_day_avg_excess_20d': down_avg_excess,
        'drawdown_advantage_60d': dd_adv,
        'rebound_advantage_60d': rebound_adv,
        'components': {k: round(v, 2) for k, v in components.items()},
    }


def leader_score(selection_score: float, relative_strength_score: float, market_regime: str, cfg: dict | None = None) -> tuple[float, float]:
    """기존 Selection을 유지하면서 TOP-N 우선순위에 상대강도를 반영한다.

    반환값: (leader_score, relative_strength_weight)
    하락장일수록 강한 종목 선별의 비중을 높인다.
    """
    cfg = cfg or {}
    if market_regime == 'downtrend':
        w = float(cfg.get('rank_weight_downtrend', 0.45))
    elif market_regime == 'volatile':
        w = float(cfg.get('rank_weight_volatile', 0.35))
    else:
        w = float(cfg.get('rank_weight_normal', 0.25))
    w = _clamp(w, 0.0, 0.80)
    score = selection_score * (1.0 - w) + relative_strength_score * w
    return round(_clamp(score, 0.0, 100.0), 2), round(w, 3)
