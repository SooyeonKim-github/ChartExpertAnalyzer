from __future__ import annotations

import argparse
from pathlib import Path

from chartsel.config import load_config
from chartsel.analysis.analyzer import ChartAnalyzer
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

    out_dir = Path(args.output_root) / f'range_{start:%Y%m%d}_{end:%Y%m%d}'
    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx = out_dir / 'chart_range_backtest.xlsx'
    csv = out_dir / 'chart_range_events.csv'
    summary_csv = out_dir / 'chart_range_summary_D1_D60.csv'
    universe_csv = out_dir / 'universe.csv'
    error_csv = out_dir / 'errors.csv'
    report = out_dir / 'chart_range_backtest.html'

    events.to_csv(csv, index=False, encoding='utf-8-sig')
    summary.to_csv(summary_csv, index=False, encoding='utf-8-sig')
    universe.to_csv(universe_csv, index=False, encoding='utf-8-sig')
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
    print('HTML Report:', report)
    if not events.empty and not events['forward_complete'].all():
        missing = int((~events['forward_complete']).sum())
        print(f'[주의] {missing}개 신호는 아직 D+{args.forward_bars} 거래일이 지나지 않아 후반 D+n 값이 비어 있습니다.')
    print('[주의] 과거 시점의 실제 시총 TOP N을 재구성한 것이 아니라 현재 KOSPI_Info.xlsx Universe를 과거에 적용합니다.')


if __name__ == '__main__':
    main()
