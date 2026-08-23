from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PositionBacktestParams:
    """이벤트 신호를 실제 보유 포지션으로 변환하는 백테스트 파라미터.

    기본 원칙
    - 신호일 종가로 매수하지 않고 다음 거래일 시가에 진입한다(실행 편향 완화).
    - 동일 종목 보유 중 발생하는 재신호는 추가 신규 포지션으로 만들지 않는다.
    - Selection은 후보 필터, Leader Rank는 실제 우선순위로 사용한다.
    - Timing은 하드 필터보다 포지션 크기 조절에 사용한다.
    - 손절/트레일링/최대 보유기간으로 청산한다.
    """
    initial_capital: float = 100_000_000.0
    min_selection: float = 70.0
    rank_top_n: int = 5
    rank_column: str = 'daily_sector_leader_rank'
    exclude_high_chase: bool = True
    max_positions: int = 5
    max_hold_bars: int = 60
    initial_stop_pct: float = 0.08
    trailing_stop_pct: float = 0.10
    trailing_activation_return: float = 0.05
    commission_rate: float = 0.00015
    sell_tax_rate: float = 0.0018
    timing_full: float = 80.0
    timing_medium: float = 70.0
    timing_small: float = 60.0
    timing_full_multiplier: float = 1.00
    timing_medium_multiplier: float = 0.80
    timing_small_multiplier: float = 0.60
    timing_low_multiplier: float = 0.40


def _timing_multiplier(timing: float, p: PositionBacktestParams) -> float:
    if timing >= p.timing_full:
        return p.timing_full_multiplier
    if timing >= p.timing_medium:
        return p.timing_medium_multiplier
    if timing >= p.timing_small:
        return p.timing_small_multiplier
    return p.timing_low_multiplier


def _safe_float(v: Any, default: float = np.nan) -> float:
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except Exception:
        return default


class PositionBacktester:
    """RangeBacktester가 만든 event DataFrame을 실제 포지션 거래로 재생한다."""

    def __init__(self, provider):
        if not hasattr(provider, 'get_ohlcv_by_date'):
            raise ValueError('PositionBacktester는 get_ohlcv_by_date를 지원하는 provider가 필요합니다.')
        self.provider = provider

    def _load_prices(self, events: pd.DataFrame, max_hold_bars: int) -> dict[str, pd.DataFrame]:
        start = pd.to_datetime(events['signal_date']).min() - pd.Timedelta(days=10)
        # 마지막 신호 이후 최대 60거래일 정도를 충분히 포함하도록 달력 버퍼 확보
        end = pd.to_datetime(events['signal_date']).max() + pd.Timedelta(days=max(120, max_hold_bars * 2 + 30))
        prices: dict[str, pd.DataFrame] = {}
        for ticker in events['ticker'].astype(str).drop_duplicates():
            df = self.provider.get_ohlcv_by_date(ticker, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if df is None or df.empty:
                continue
            x = df.copy()
            x.index = pd.to_datetime(x.index).normalize()
            x = x[~x.index.duplicated(keep='last')].sort_index()
            prices[ticker] = x
        return prices

    @staticmethod
    def _next_trade_date(df: pd.DataFrame, signal_date: pd.Timestamp) -> pd.Timestamp | None:
        idx = df.index.searchsorted(signal_date, side='right')
        if idx >= len(df.index):
            return None
        return pd.Timestamp(df.index[idx]).normalize()

    def run(self, events: pd.DataFrame, params: PositionBacktestParams | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
        p = params or PositionBacktestParams()
        if events is None or events.empty:
            return pd.DataFrame(), pd.DataFrame(), self._empty_summary(p.initial_capital)

        ev = events.copy()
        ev['signal_date'] = pd.to_datetime(ev['signal_date']).dt.normalize()
        if 'selection_score' not in ev.columns:
            raise ValueError('events에 selection_score 컬럼이 필요합니다.')
        if p.rank_column not in ev.columns:
            fallback = next((c for c in ['daily_leader_rank', 'daily_rank'] if c in ev.columns), None)
            if fallback is None:
                raise ValueError(f'events에 {p.rank_column}, daily_leader_rank 또는 daily_rank 컬럼이 필요합니다.')
            rank_col = fallback
        else:
            rank_col = p.rank_column

        ev = ev[pd.to_numeric(ev['selection_score'], errors='coerce') >= p.min_selection].copy()
        ev = ev[pd.to_numeric(ev[rank_col], errors='coerce') <= p.rank_top_n].copy()
        if p.exclude_high_chase and 'chase_risk' in ev.columns:
            ev = ev[ev['chase_risk'].astype(str) != '높음'].copy()
        if ev.empty:
            return pd.DataFrame(), pd.DataFrame(), self._empty_summary(p.initial_capital)

        prices = self._load_prices(ev, p.max_hold_bars)
        if not prices:
            return pd.DataFrame(), pd.DataFrame(), self._empty_summary(p.initial_capital)

        # 각 신호는 다음 거래일 시가 주문 후보가 된다.
        pending_by_date: dict[pd.Timestamp, list[dict[str, Any]]] = {}
        for _, row in ev.iterrows():
            ticker = str(row['ticker'])
            df = prices.get(ticker)
            if df is None:
                continue
            exec_date = self._next_trade_date(df, row['signal_date'])
            if exec_date is None:
                continue
            item = row.to_dict()
            item['exec_date'] = exec_date
            pending_by_date.setdefault(exec_date, []).append(item)

        if not pending_by_date:
            return pd.DataFrame(), pd.DataFrame(), self._empty_summary(p.initial_capital)

        # 실제 시뮬레이션 달력은 모든 종목의 거래일 합집합을 사용한다.
        start_date = min(pending_by_date)
        max_signal = ev['signal_date'].max()
        sim_end = max_signal + pd.Timedelta(days=max(120, p.max_hold_bars * 2 + 30))
        calendar = sorted({d for df in prices.values() for d in df.index if start_date <= d <= sim_end})

        cash = float(p.initial_capital)
        positions: dict[str, dict[str, Any]] = {}
        trades: list[dict[str, Any]] = []
        equity_rows: list[dict[str, Any]] = []
        last_close: dict[str, float] = {}

        def current_equity() -> float:
            value = cash
            for ticker, pos in positions.items():
                px = last_close.get(ticker, pos['entry_price'])
                value += pos['shares'] * px
            return float(value)

        for date in calendar:
            # 먼저 현재일 가격을 업데이트한다.
            for ticker, df in prices.items():
                if date in df.index:
                    last_close[ticker] = float(df.loc[date, 'Close'])

            # 1) 기존 포지션 청산 판단. 새 진입보다 먼저 처리해 현금을 재사용할 수 있게 한다.
            for ticker in list(positions):
                pos = positions[ticker]
                df = prices[ticker]
                if date not in df.index or date <= pos['entry_date']:
                    continue
                bar = df.loc[date]
                open_px = float(bar['Open']); low_px = float(bar['Low']); close_px = float(bar['Close'])

                stop = float(pos['initial_stop'])
                if pos['trailing_active']:
                    stop = max(stop, float(pos['trailing_stop']))

                exit_reason = None
                exit_price = None
                if open_px <= stop:
                    exit_reason = 'stop_gap'
                    exit_price = open_px
                elif low_px <= stop:
                    exit_reason = 'stop_or_trailing'
                    exit_price = stop
                elif pos['bars_held'] >= p.max_hold_bars:
                    exit_reason = 'max_hold'
                    exit_price = close_px

                if exit_reason is not None:
                    gross = pos['shares'] * exit_price
                    sell_cost = gross * (p.commission_rate + p.sell_tax_rate)
                    cash += gross - sell_cost
                    pnl = (gross - sell_cost) - pos['entry_cost_total']
                    ret = pnl / pos['entry_cost_total'] if pos['entry_cost_total'] else np.nan
                    trades.append({
                        'ticker': ticker,
                        'name': pos.get('name', ''),
                        'signal_date': pos['signal_date'],
                        'entry_date': pos['entry_date'],
                        'exit_date': date,
                        'entry_price': pos['entry_price'],
                        'exit_price': exit_price,
                        'shares': pos['shares'],
                        'position_value': pos['entry_value'],
                        'timing_score': pos['timing_score'],
                        'selection_score': pos['selection_score'],
                        'relative_strength_score': pos.get('relative_strength_score', np.nan),
                        'leader_score': pos.get('leader_score', np.nan),
                        'sector_name': pos.get('sector_name', ''),
                        'sector_rs_score': pos.get('sector_rs_score', np.nan),
                        'sector_composite_score': pos.get('sector_composite_score', np.nan),
                        'sector_leader_score': pos.get('sector_leader_score', np.nan),
                        'is_true_leader': pos.get('is_true_leader', False),
                        'rank_at_signal': pos.get('rank_at_signal', np.nan),
                        'bars_held': pos['bars_held'],
                        'exit_reason': exit_reason,
                        'pnl': pnl,
                        'return': ret,
                    })
                    del positions[ticker]
                    continue

                # 오늘 종가까지 살아남은 포지션은 보유일수와 최고 종가를 갱신한다.
                pos['bars_held'] += 1
                pos['highest_close'] = max(float(pos['highest_close']), close_px)
                if pos['highest_close'] / pos['entry_price'] - 1.0 >= p.trailing_activation_return:
                    pos['trailing_active'] = True
                    pos['trailing_stop'] = pos['highest_close'] * (1.0 - p.trailing_stop_pct)

            # 2) 다음 거래일 시가 진입. 선택한 rank_column의 순위를 가장 우선한다.
            # V3 daily_sector_leader_rank를 쓰면 Sector Leader 순서가 실제 주문 순서에도 반영된다.
            candidates = pending_by_date.get(date, [])
            candidates = sorted(
                candidates,
                key=lambda r: (
                    _safe_float(r.get(rank_col), 999999.0),
                    -_safe_float(r.get('sector_leader_score'), _safe_float(r.get('leader_score'), _safe_float(r.get('selection_score'), 0.0))),
                    -_safe_float(r.get('selection_score'), 0.0),
                ),
            )
            for row in candidates:
                if len(positions) >= p.max_positions:
                    break
                ticker = str(row['ticker'])
                if ticker in positions:
                    continue
                df = prices.get(ticker)
                if df is None or date not in df.index:
                    continue
                open_px = float(df.loc[date, 'Open'])
                if not np.isfinite(open_px) or open_px <= 0:
                    continue

                timing = _safe_float(row.get('timing_score'), 50.0)
                mult = _timing_multiplier(timing, p)
                eq = current_equity()
                target = eq / max(1, p.max_positions) * mult
                target = min(target, cash / (1.0 + p.commission_rate))
                shares = int(target // open_px)
                if shares <= 0:
                    continue
                entry_value = shares * open_px
                buy_cost = entry_value * p.commission_rate
                total = entry_value + buy_cost
                if total > cash:
                    continue
                cash -= total

                raw_stop = _safe_float(row.get('stop_price'))
                default_stop = open_px * (1.0 - p.initial_stop_pct)
                # 신호일 기준 stop이 다음날 갭 상승으로 지나치게 멀어지거나 진입가 위에 있으면 기본 손절 사용.
                if not np.isfinite(raw_stop) or raw_stop >= open_px or raw_stop < open_px * (1.0 - 0.20):
                    init_stop = default_stop
                else:
                    init_stop = max(raw_stop, default_stop)

                positions[ticker] = {
                    'ticker': ticker,
                    'name': row.get('name', ''),
                    'signal_date': pd.Timestamp(row['signal_date']).normalize(),
                    'entry_date': date,
                    'entry_price': open_px,
                    'entry_value': entry_value,
                    'entry_cost_total': total,
                    'shares': shares,
                    'timing_score': timing,
                    'selection_score': _safe_float(row.get('selection_score'), np.nan),
                    'relative_strength_score': _safe_float(row.get('relative_strength_score'), np.nan),
                    'leader_score': _safe_float(row.get('leader_score'), np.nan),
                    'sector_name': row.get('sector_name', ''),
                    'sector_rs_score': _safe_float(row.get('sector_rs_score'), np.nan),
                    'sector_composite_score': _safe_float(row.get('sector_composite_score'), np.nan),
                    'sector_leader_score': _safe_float(row.get('sector_leader_score'), np.nan),
                    'is_true_leader': bool(row.get('is_true_leader', False)),
                    'rank_at_signal': _safe_float(row.get(rank_col), np.nan),
                    'initial_stop': init_stop,
                    'highest_close': float(df.loc[date, 'Close']),
                    'trailing_active': False,
                    'trailing_stop': np.nan,
                    'bars_held': 1,
                }

            equity_rows.append({
                'date': date,
                'equity': current_equity(),
                'cash': cash,
                'position_count': len(positions),
            })

        # 시뮬레이션 끝에 남은 포지션은 마지막 가능한 종가로 청산해 성과를 확정한다.
        for ticker in list(positions):
            pos = positions[ticker]
            df = prices[ticker]
            usable = df[df.index >= pos['entry_date']]
            if usable.empty:
                continue
            date = usable.index[-1]
            exit_price = float(usable['Close'].iloc[-1])
            gross = pos['shares'] * exit_price
            sell_cost = gross * (p.commission_rate + p.sell_tax_rate)
            cash += gross - sell_cost
            pnl = (gross - sell_cost) - pos['entry_cost_total']
            ret = pnl / pos['entry_cost_total'] if pos['entry_cost_total'] else np.nan
            trades.append({
                'ticker': ticker, 'name': pos.get('name', ''), 'signal_date': pos['signal_date'],
                'entry_date': pos['entry_date'], 'exit_date': date, 'entry_price': pos['entry_price'],
                'exit_price': exit_price, 'shares': pos['shares'], 'position_value': pos['entry_value'],
                'timing_score': pos['timing_score'], 'selection_score': pos['selection_score'],
                'relative_strength_score': pos.get('relative_strength_score', np.nan),
                'leader_score': pos.get('leader_score', np.nan), 'sector_name': pos.get('sector_name', ''),
                'sector_rs_score': pos.get('sector_rs_score', np.nan), 'sector_composite_score': pos.get('sector_composite_score', np.nan),
                'sector_leader_score': pos.get('sector_leader_score', np.nan), 'is_true_leader': pos.get('is_true_leader', False),
                'rank_at_signal': pos.get('rank_at_signal', np.nan),
                'bars_held': pos['bars_held'], 'exit_reason': 'simulation_end', 'pnl': pnl, 'return': ret,
            })
            del positions[ticker]

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_rows)
        if not equity_df.empty:
            equity_df = equity_df.drop_duplicates('date', keep='last').sort_values('date').reset_index(drop=True)
            equity_df['peak'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = equity_df['equity'] / equity_df['peak'] - 1.0
            # 마지막 강제청산 비용까지 반영
            equity_df.loc[equity_df.index[-1], 'equity'] = cash
            equity_df.loc[equity_df.index[-1], 'cash'] = cash
            equity_df.loc[equity_df.index[-1], 'position_count'] = 0
            equity_df['peak'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = equity_df['equity'] / equity_df['peak'] - 1.0

        summary = self._summary(trades_df, equity_df, p.initial_capital, cash)
        return trades_df, equity_df, summary

    @staticmethod
    def _empty_summary(initial_capital: float) -> dict[str, float]:
        return {
            'initial_capital': float(initial_capital),
            'final_equity': float(initial_capital),
            'total_return': 0.0,
            'max_drawdown': 0.0,
            'trade_count': 0,
            'win_rate': np.nan,
            'avg_trade_return': np.nan,
            'median_trade_return': np.nan,
            'profit_factor': np.nan,
        }

    @staticmethod
    def _summary(trades: pd.DataFrame, equity: pd.DataFrame, initial: float, final_cash: float) -> dict[str, float]:
        if trades.empty:
            return PositionBacktester._empty_summary(initial)
        wins = trades.loc[trades['pnl'] > 0, 'pnl']
        losses = trades.loc[trades['pnl'] < 0, 'pnl']
        profit_factor = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.inf
        max_dd = float(equity['drawdown'].min()) if not equity.empty else np.nan
        return {
            'initial_capital': float(initial),
            'final_equity': float(final_cash),
            'total_return': float(final_cash / initial - 1.0),
            'max_drawdown': max_dd,
            'trade_count': int(len(trades)),
            'win_rate': float((trades['pnl'] > 0).mean()),
            'avg_trade_return': float(pd.to_numeric(trades['return'], errors='coerce').mean()),
            'median_trade_return': float(pd.to_numeric(trades['return'], errors='coerce').median()),
            'profit_factor': profit_factor,
        }
