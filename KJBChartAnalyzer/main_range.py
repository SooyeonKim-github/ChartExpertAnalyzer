from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from chartsel.config import load_config
from chartsel.analysis.analyzer import ChartAnalyzer
from chartsel.analysis.market_regime import classify_market_regime
from chartsel.data.pykrx_provider import PykrxDataProvider
from chartsel.universe.ticker_universe_service import TickerUniverseService
from chartsel.backtest.range_engine import RangeBacktester, RangeBacktestParams, parse_date_range, key_horizon_summary
from chartsel.backtest.range_report import save_range_backtest_excel, save_range_backtest_html

ROOT = Path(__file__).resolve().parent


def build_parser():
    p = argparse.ArgumentParser(description='기간 입력형 TOP N 차트 신호 백테스트')
    p.add_argument('--date-range', required=True, help='YYYYMMDD~YYYYMMDD')
    p.add_argument('--top-n', type=int, default=100)
    p.add_argument('--sort-by', choices=['market_cap','trading_value','volume'], default='market_cap')
    p.add_argument('--forward-bars', type=int, default=60, help='D+N 거래일 수익률. 기본 60')
    p.add_argument('--history-days', type=int, default=1200, help='신호일 이전 확보할 달력 일수')
    p.add_argument('--cooldown-bars', type=int, default=0, help='같은 종목 연속 신호 간 최소 거래일 간격. 0=모든 신호')
    p.add_argument('--min-score', type=float, default=None)
    p.add_argument('--min-technical', type=float, default=None)
    p.add_argument('--min-timing', type=float, default=None)
    p.add_argument('--max-risk', type=float, default=None)
    p.add_argument('--include-etf', action='store_true')
    p.add_argument('--info-excel', default=str(ROOT/'KOSPI_Info.xlsx'))
    p.add_argument('--cache-dir', default=str(ROOT/'cache'))
    p.add_argument('--no-cache', action='store_true')
    p.add_argument('--config', default=None)
    p.add_argument('--output-root', default=str(ROOT/'results'))
    return p


def _fetch_bounds(start: pd.Timestamp, end: pd.Timestamp, history_days: int, forward_bars: int) -> tuple[str, str]:
    fetch_start = (start - pd.Timedelta(days=int(history_days))).strftime('%Y-%m-%d')
    forward_calendar_days = max(120, int(int(forward_bars) * 2.0))
    fetch_end = (end + pd.Timedelta(days=forward_calendar_days)).strftime('%Y-%m-%d')
    return fetch_start, fetch_end


def _normalize_market(value) -> str:
    text = str(value or '').strip().upper()
    if 'KOSDAQ' in text or text in {'KQ', '^KQ11', '2001'}:
        return 'KOSDAQ'
    if 'KOSPI' in text or text in {'KS', '^KS11', '1001'}:
        return 'KOSPI'
    return ''


def _build_market_regime_daily(
    provider: PykrxDataProvider,
    analyzer: ChartAnalyzer,
    start: pd.Timestamp,
    end: pd.Timestamp,
    history_days: int,
    forward_bars: int,
) -> pd.DataFrame:
    """각 거래일 시점까지의 지수 데이터만 사용해 시장 Regime/Stretch를 계산한다."""
    rows: list[dict] = []
    fetch_start, fetch_end = _fetch_bounds(start, end, history_days, forward_bars)
    min_hist = max(int(analyzer.cfg['moving_average']['long']) + 10, 140)

    for market, benchmark in [('KOSPI', '^KS11'), ('KOSDAQ', '^KQ11')]:
        try:
            raw = provider.get_ohlcv_by_date(benchmark, fetch_start, fetch_end)
            if raw is None or raw.empty:
                raise ValueError('시장지수 데이터 없음')
            raw = raw.copy()
            raw.index = pd.to_datetime(raw.index).normalize()
            raw = raw[~raw.index.duplicated(keep='last')].sort_index()
            close = pd.to_numeric(raw['Close'], errors='coerce')

            target_dates = raw.index[(raw.index >= start) & (raw.index <= end)]
            for signal_date in target_dates:
                hist = raw.loc[raw.index <= signal_date].copy()
                hclose = pd.to_numeric(hist['Close'], errors='coerce').dropna()
                current = float(hclose.iloc[-1]) if not hclose.empty else float('nan')
                ret5 = float(current / hclose.iloc[-6] - 1.0) if len(hclose) >= 6 else np.nan
                ret20 = float(current / hclose.iloc[-21] - 1.0) if len(hclose) >= 21 else np.nan
                high20 = float(hclose.tail(20).max()) if len(hclose) >= 1 else np.nan
                drawdown20 = float(current / high20 - 1.0) if np.isfinite(high20) and high20 else np.nan
                ma20 = float(hclose.tail(20).mean()) if len(hclose) >= 20 else np.nan
                ma60 = float(hclose.tail(60).mean()) if len(hclose) >= 60 else np.nan
                gap20 = float(current / ma20 - 1.0) if np.isfinite(ma20) and ma20 else np.nan
                gap60 = float(current / ma60 - 1.0) if np.isfinite(ma60) and ma60 else np.nan
                returns = hclose.pct_change().dropna()
                vol20 = float(returns.tail(20).std()) if len(returns) >= 20 else np.nan
                vol120 = float(returns.tail(120).std()) if len(returns) >= 120 else np.nan

                if len(hist) < min_hist:
                    regime = 'unknown'
                    warning = f'히스토리 부족({len(hist)}<{min_hist})'
                else:
                    try:
                        prepared = analyzer.prepare(hist)
                        regime = classify_market_regime(prepared, analyzer.cfg['moving_average'])
                        warning = ''
                    except Exception as exc:
                        regime = 'unknown'
                        warning = str(exc)

                rows.append({
                    'date': pd.Timestamp(signal_date).normalize(),
                    'market': market,
                    'benchmark': benchmark,
                    'market_regime': regime,
                    'index_close': current,
                    'index_return_5d': ret5,
                    'index_return_20d': ret20,
                    'index_drawdown_20d': drawdown20,
                    'index_ma20_gap': gap20,
                    'index_ma60_gap': gap60,
                    'index_volatility_20d': vol20,
                    'index_volatility_120d': vol120,
                    'history_bars': int(len(hist)),
                    'regime_warning': warning,
                })
        except Exception as exc:
            rows.append({
                'date': pd.NaT,
                'market': market,
                'benchmark': benchmark,
                'market_regime': 'unknown',
                'index_close': float('nan'),
                'index_return_5d': np.nan,
                'index_return_20d': np.nan,
                'index_drawdown_20d': np.nan,
                'index_ma20_gap': np.nan,
                'index_ma60_gap': np.nan,
                'index_volatility_20d': np.nan,
                'index_volatility_120d': np.nan,
                'history_bars': 0,
                'regime_warning': f'시장지수 조회 실패: {exc}',
            })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(['date', 'market'], na_position='last').reset_index(drop=True)
    return out


def _build_market_breadth_daily(
    provider: PykrxDataProvider,
    universe: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    history_days: int,
    forward_bars: int,
) -> pd.DataFrame:
    """Range Universe 내부 종목으로 point-in-time breadth를 계산한다.

    RangeBacktester와 동일 provider/조회구간을 사용하므로 이미 받은 종목 데이터는
    memory cache를 재사용한다. 신호일 이후 데이터는 각 지표 계산에 사용하지 않는다.
    """
    if universe is None or universe.empty:
        return pd.DataFrame()

    fetch_start, fetch_end = _fetch_bounds(start, end, history_days, forward_bars)
    records: list[pd.DataFrame] = []

    for row in universe.itertuples(index=False):
        ticker = str(getattr(row, 'ticker', '')).strip().zfill(6)
        market = _normalize_market(getattr(row, 'market', ''))
        if not ticker or not market:
            continue
        try:
            raw = provider.get_ohlcv_by_date(ticker, fetch_start, fetch_end)
            if raw is None or raw.empty:
                continue
            x = raw.copy()
            x.index = pd.to_datetime(x.index).normalize()
            x = x[~x.index.duplicated(keep='last')].sort_index()
            close = pd.to_numeric(x['Close'], errors='coerce')
            ma20 = close.rolling(20, min_periods=20).mean()
            ma60 = close.rolling(60, min_periods=60).mean()
            ret5 = close.pct_change(5)
            ret20 = close.pct_change(20)

            target = pd.DataFrame(index=x.index)
            target['ticker'] = ticker
            target['market'] = market
            target['above_ma20'] = np.where(ma20.notna(), (close > ma20).astype(float), np.nan)
            target['above_ma60'] = np.where(ma60.notna(), (close > ma60).astype(float), np.nan)
            target['positive_5d'] = np.where(ret5.notna(), (ret5 > 0).astype(float), np.nan)
            target['positive_20d'] = np.where(ret20.notna(), (ret20 > 0).astype(float), np.nan)
            target = target[(target.index >= start) & (target.index <= end)]
            if target.empty:
                continue
            target = target.reset_index().rename(columns={'index': 'date'})
            records.append(target)
        except Exception:
            continue

    if not records:
        return pd.DataFrame()

    detail = pd.concat(records, ignore_index=True)
    grouped = detail.groupby(['date', 'market'], as_index=False).agg(
        breadth_stock_count=('ticker', 'nunique'),
        breadth_valid_ma20=('above_ma20', 'count'),
        breadth_valid_ma60=('above_ma60', 'count'),
        breadth_above_ma20_ratio=('above_ma20', 'mean'),
        breadth_above_ma60_ratio=('above_ma60', 'mean'),
        breadth_positive_5d_ratio=('positive_5d', 'mean'),
        breadth_positive_20d_ratio=('positive_20d', 'mean'),
    )
    return grouped.sort_values(['date', 'market']).reset_index(drop=True)


def main():
    args = build_parser().parse_args()
    start, end = parse_date_range(args.date_range)
    cfg = load_config(args.config)
    min_score = float(args.min_score if args.min_score is not None else cfg['selection']['min_score'])

    params = RangeBacktestParams(
        start_date=start, end_date=end, top_n=args.top_n, sort_by=args.sort_by,
        forward_bars=args.forward_bars, history_days=args.history_days,
        min_score=min_score, min_technical=args.min_technical, min_timing=args.min_timing,
        max_risk=args.max_risk, cooldown_bars=args.cooldown_bars,
    )

    provider = PykrxDataProvider(cache_dir=args.cache_dir, use_cache=not args.no_cache)
    analyzer = ChartAnalyzer(cfg)
    universe_service = TickerUniverseService(args.info_excel)
    runner = RangeBacktester(analyzer, provider, universe_service)

    print('='*78)
    print('차트 신호 기간 백테스트')
    print('='*78)
    print(f'기간          : {start:%Y-%m-%d} ~ {end:%Y-%m-%d}')
    print(f'Universe      : {args.sort_by} TOP {args.top_n}')
    print(f'사후수익률    : D+1 ~ D+{args.forward_bars} 거래일')
    print(f'Selection 최소: {min_score:.1f}')
    print(f'Technical 최소: {args.min_technical if args.min_technical is not None else "미사용"}')
    print(f'Timing 최소   : {args.min_timing if args.min_timing is not None else "미사용"}')
    print(f'Risk 최대     : {args.max_risk if args.max_risk is not None else "미사용"}')
    print()

    events, summary, universe, errors = runner.run(params, include_etf=args.include_etf)
    market_regime_daily = _build_market_regime_daily(
        provider, analyzer, start, end, args.history_days, args.forward_bars
    )
    market_breadth_daily = _build_market_breadth_daily(
        provider, universe, start, end, args.history_days, args.forward_bars
    )
    if not market_breadth_daily.empty:
        market_regime_daily = market_regime_daily.merge(
            market_breadth_daily, on=['date', 'market'], how='left'
        )

    out_dir = Path(args.output_root) / f'range_{start:%Y%m%d}_{end:%Y%m%d}'
    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx = out_dir / 'chart_range_backtest.xlsx'
    csv = out_dir / 'chart_range_events.csv'
    summary_csv = out_dir / 'chart_range_summary_D1_D60.csv'
    universe_csv = out_dir / 'universe.csv'
    error_csv = out_dir / 'errors.csv'
    regime_csv = out_dir / 'market_regime_daily.csv'
    breadth_csv = out_dir / 'market_breadth_daily.csv'
    report = out_dir / 'chart_range_backtest.html'

    events.to_csv(csv, index=False, encoding='utf-8-sig')
    summary.to_csv(summary_csv, index=False, encoding='utf-8-sig')
    universe.to_csv(universe_csv, index=False, encoding='utf-8-sig')
    market_regime_daily.to_csv(regime_csv, index=False, encoding='utf-8-sig')
    market_breadth_daily.to_csv(breadth_csv, index=False, encoding='utf-8-sig')
    if not errors.empty:
        errors.to_csv(error_csv, index=False, encoding='utf-8-sig')

    meta = {
        '기간': f'{start:%Y-%m-%d} ~ {end:%Y-%m-%d}',
        'Universe': f'{args.sort_by} TOP {args.top_n}',
        'D+수익률': f'D+1 ~ D+{args.forward_bars} 거래일',
        'Selection 최소': min_score,
        'Technical 최소': args.min_technical if args.min_technical is not None else '미사용',
        'Timing 최소': args.min_timing if args.min_timing is not None else '미사용',
        'Risk 최대': args.max_risk if args.max_risk is not None else '미사용',
        'Cooldown': args.cooldown_bars,
        '신호수': len(events),
        'D+60 완전표본': int(events['forward_complete'].sum()) if not events.empty else 0,
        'Universe 주의': 'KOSPI_Info.xlsx 현재 스냅샷 고정 Universe',
        '시장 Regime': 'KOSPI/KOSDAQ별 일별 point-in-time 판정; 미래 데이터 미사용',
        '시장 Breadth': 'Range Universe 내부 MA20/MA60/5D/20D breadth; 미래 데이터 미사용',
    }
    save_range_backtest_excel(events, summary, universe, errors, xlsx, meta)
    save_range_backtest_html(events, summary, report, meta)

    print('\n[핵심 사후수익률]')
    ks = key_horizon_summary(summary)
    if ks.empty:
        print('조건 충족 신호 없음')
    else:
        view = ks[['horizon','valid_count','avg_return','median_return','win_rate']].copy()
        for c in ['avg_return','median_return','win_rate']:
            view[c] = view[c].map(lambda x: '-' if x != x else f'{x*100:.2f}%')
        print(view.to_string(index=False))

    print('\n[완료]')
    print('상세 Excel :', xlsx)
    print('상세 CSV   :', csv)
    print('통계 CSV   :', summary_csv)
    print('시장 Regime:', regime_csv)
    print('시장 Breadth:', breadth_csv)
    print('HTML Report:', report)
    if not events.empty and not events['forward_complete'].all():
        missing = int((~events['forward_complete']).sum())
        print(f'[주의] {missing}개 신호는 아직 D+{args.forward_bars} 거래일이 지나지 않아 후반 D+n 값이 비어 있습니다.')
    print('[주의] 과거 시점의 실제 시총 TOP N을 재구성한 것이 아니라 현재 KOSPI_Info.xlsx Universe를 과거에 적용합니다.')


if __name__ == '__main__':
    main()
