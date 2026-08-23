from __future__ import annotations

import pandas as pd


def calendar_start_for_history(target_date: str, days: int = 520) -> str:
    return (pd.Timestamp(target_date) - pd.Timedelta(days=days)).strftime('%Y-%m-%d')


def calendar_end_for_backtest(target_date: str, days: int = 45) -> str:
    return (pd.Timestamp(target_date) + pd.Timedelta(days=days)).strftime('%Y-%m-%d')


def period_to_date_range(period: str = '5y', end_date: str | None = None) -> tuple[str, str]:
    """CLI의 6mo/1y/2y/5y/10y 형식을 pykrx 날짜 범위로 변환한다."""
    end = pd.Timestamp(end_date).normalize() if end_date else pd.Timestamp.today().normalize()
    text = str(period).strip().lower()
    if text == 'max':
        start = pd.Timestamp('1990-01-01')
    elif text.endswith('y'):
        start = end - pd.DateOffset(years=int(text[:-1]))
    elif text.endswith('mo'):
        start = end - pd.DateOffset(months=int(text[:-2]))
    elif text.endswith('d'):
        start = end - pd.Timedelta(days=int(text[:-1]))
    else:
        raise ValueError(f'지원하지 않는 period 형식: {period} (예: 6mo, 1y, 5y, 10y, max)')
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')
