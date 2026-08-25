from __future__ import annotations

import argparse
from pathlib import Path
import re

from chartsel.config import load_config
from chartsel.data.csv_provider import CSVProvider
from chartsel.data.yfinance_provider import YFinanceProvider
from chartsel.data.pykrx_provider import PykrxDataProvider
from chartsel.analysis.analyzer import ChartAnalyzer
from chartsel.selection.selector import StockSelector
from chartsel.reporting.report import print_result, save_result_json, save_screen_csv
from chartsel.reporting.agent_exporter import export_agent_candidates
from chartsel.reporting.html_report import save_analysis_html, save_screen_html
from chartsel.backtest.engine import SimpleBacktester
from chartsel.reporting.plot import plot_analysis
from chartsel.universe.ticker_universe_service import TickerUniverseService


ROOT = Path(__file__).resolve().parent
DEFAULT_INFO_EXCEL = ROOT / 'KOSPI_Info.xlsx'


def provider_from_args(args):
    if args.provider == 'csv':
        if not args.data_dir:
            raise ValueError('--provider csv 사용 시 --data-dir 필요')
        return CSVProvider(args.data_dir)
    if args.provider == 'pykrx':
        return PykrxDataProvider(
            cache_dir=getattr(args, 'cache_dir', None),
            use_cache=not getattr(args, 'no_cache', False),
            end_date=getattr(args, 'end_date', None),
        )
    return YFinanceProvider()


def _agent_output_dir(args) -> Path:
    if getattr(args, 'out', None):
        return Path(args.out).parent
    return ROOT / 'output'


def _safe_filename(value: str) -> str:
    return re.sub(r'[^0-9A-Za-z가-힣._-]+', '_', str(value or '')).strip('_')


def _save_confirmed_charts(table, selector: StockSelector, analyzer: ChartAnalyzer, out_dir: Path) -> list[Path]:
    """현재 스크린의 CONFIRMED 종목만 차트로 저장한다.

    StockSelector가 분석 시 보관한 OHLCV/result를 재사용하므로 추가 데이터 조회는 하지 않는다.
    이전 실행의 PNG는 삭제해 현재 CONFIRMED 결과와 섞이지 않게 한다.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob('*.png'):
        try:
            old.unlink()
        except OSError:
            pass

    if table.empty or 'Status' not in table.columns:
        print('CONFIRMED 차트: 대상 없음')
        return []

    confirmed = table[table['Status'].eq('CONFIRMED')].copy()
    paths: list[Path] = []
    for _, row in confirmed.iterrows():
        ticker = str(row.get('ticker', '')).strip()
        cached = selector.last_analysis.get(ticker)
        if cached is None:
            print(f'[WARN] CONFIRMED 차트 캐시 없음: {ticker}')
            continue
        raw_df, result = cached
        try:
            prepared = analyzer.prepare(raw_df)
            name = _safe_filename(row.get('name', ''))
            stem = f'{ticker}_{name}_CONFIRMED' if name else f'{ticker}_CONFIRMED'
            path = out_dir / f'{stem}.png'
            plot_analysis(prepared, result, str(path), status='CONFIRMED')
            paths.append(path)
        except Exception as exc:
            print(f'[WARN] CONFIRMED 차트 생성 실패 {ticker}: {exc}')

    print(f'CONFIRMED: {len(confirmed)}종목 | 차트: {len(paths)}개')
    if paths:
        print(f'CONFIRMED Charts: {out_dir}')
    return paths


def cmd_analyze(args):
    cfg = load_config(args.config)
    provider = provider_from_args(args)
    analyzer = ChartAnalyzer(cfg)
    df = provider.get_ohlcv(args.ticker, period=args.period)
    market_df = None
    if args.market:
        try:
            market_df = provider.get_ohlcv(args.market, period=args.period)
        except Exception as e:
            print('시장 데이터 경고:', e)
    r = analyzer.analyze(args.ticker, df, market_df)
    print_result(r)
    if args.out:
        save_result_json(r, args.out)

    chart_path = args.chart
    if args.report and not chart_path:
        chart_path = str(Path(args.report).with_name(Path(args.report).stem + '_chart.png'))
    if chart_path:
        prepared = analyzer.prepare(df)
        plot_analysis(prepared, r, chart_path)
    if args.report:
        save_analysis_html(r, args.report, chart_path)
        print(f'\nHTML 상세 리포트: {args.report}')


def cmd_screen(args):
    cfg = load_config(args.config)
    provider = provider_from_args(args)
    analyzer = ChartAnalyzer(cfg)
    selector = StockSelector(analyzer, provider, cfg)
    tickers = [
        x.strip()
        for x in Path(args.tickers).read_text(encoding='utf-8-sig').splitlines()
        if x.strip() and not x.startswith('#')
    ]
    table, errors = selector.screen(tickers, args.period, args.market, args.max_results)
    _print_screen(table)
    if args.out:
        save_screen_csv(table, args.out)
    if args.report:
        save_screen_html(table, args.report)
        print(f'\nHTML 랭킹 리포트: {args.report}')
    _save_confirmed_charts(table, selector, analyzer, _agent_output_dir(args) / 'confirmed_charts')
    agent_json, agent_md = export_agent_candidates(table, _agent_output_dir(args), args.agent_top_n)
    print(f'Agent JSON: {agent_json}')
    print(f'Agent MD  : {agent_md}')
    _print_errors(errors)


def cmd_screen_top(args):
    """KOSPI_Info.xlsx에서 지정 기준 TOP N을 만들고 바로 차트 선별을 실행한다."""
    cfg = load_config(args.config)
    provider = provider_from_args(args)
    analyzer = ChartAnalyzer(cfg)
    selector = StockSelector(analyzer, provider, cfg)
    universe_service = TickerUniverseService(args.info_excel)
    universe = universe_service.get_universe(
        top_n=args.top_n,
        sort_by=args.sort_by,
        include_etf=args.include_etf,
    )
    print(f'Universe: {args.info_excel}')
    print(f'정렬기준: {args.sort_by} | 분석대상: {len(universe)}종목 | ETF 포함: {args.include_etf}')
    if universe:
        print('상위 10종목:', ', '.join(f'{x.name}({x.ticker})' for x in universe[:10]))

    table, errors = selector.screen_universe(
        universe,
        period=args.period,
        limit=args.max_results,
    )
    _print_screen(table, with_meta=True)
    if args.universe_out:
        _save_universe(universe, args.universe_out)
    if args.out:
        save_screen_csv(table, args.out)
    if args.report:
        save_screen_html(table, args.report)
        print(f'\nHTML TOP{args.top_n} 랭킹 리포트: {args.report}')
    _save_confirmed_charts(table, selector, analyzer, _agent_output_dir(args) / 'confirmed_charts')
    agent_json, agent_md = export_agent_candidates(table, _agent_output_dir(args), args.agent_top_n)
    print(f'Agent JSON: {agent_json}')
    print(f'Agent MD  : {agent_md}')
    _print_errors(errors)


def _save_universe(universe, out_path: str):
    import pandas as pd
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        'source_rank': x.source_rank,
        'ticker': x.ticker,
        'name': x.name,
        'market': x.market,
        'market_cap': x.market_cap,
        'trading_value': x.trading_value,
        'volume': x.volume,
    } for x in universe]).to_csv(p, index=False, encoding='utf-8-sig')
    print(f'Universe CSV: {p}')


def _print_screen(table, with_meta: bool = False):
    if table.empty:
        print('선별 결과 없음')
        return
    cols = []
    if with_meta:
        cols += ['source_rank', 'ticker', 'name', 'market', 'market_cap']
    else:
        cols += ['ticker']
    cols += [
        'Status', 'score', 'technical_score', 'timing_score', 'risk_score',
        'relative_strength_score', 'leader_score', 'chase_risk', 'action',
        'market_regime', 'close'
    ]
    cols = [c for c in cols if c in table.columns]
    print(table[cols].to_string(index=False))


def _print_errors(errors):
    if errors:
        print(f'\n[오류 {len(errors)}건]')
        for t, e in errors:
            print(t, e)


def cmd_backtest(args):
    cfg = load_config(args.config)
    provider = provider_from_args(args)
    analyzer = ChartAnalyzer(cfg)
    df = provider.get_ohlcv(args.ticker, period=args.period)
    bt = SimpleBacktester(analyzer).event_study(
        args.ticker, df, min_score=args.min_score,
        min_technical=args.min_technical, min_timing=args.min_timing, max_risk=args.max_risk
    )
    if bt.empty:
        print('조건을 충족한 이벤트가 없습니다.')
        return
    print(bt.tail(30).to_string(index=False))
    print('\n[평균 사후수익률]')
    for c in [c for c in bt.columns if c.startswith('ret_')]:
        print(c, f'{bt[c].mean()*100:.2f}%', '승률', f'{(bt[c] > 0).mean()*100:.1f}%')
    print('\n[선별 신호 평균]')
    for c in ['score', 'technical_score', 'timing_score', 'risk_score', 'confluence_score']:
        print(c, f'{bt[c].mean():.1f}')
    if args.out:
        bt.to_csv(args.out, index=False, encoding='utf-8-sig')


def _add_provider_options(sp, default='yfinance'):
    sp.add_argument('--provider', choices=['yfinance', 'pykrx', 'csv'], default=default)
    sp.add_argument('--data-dir', default=None)
    sp.add_argument('--cache-dir', default=None, help='pykrx 캐시 폴더')
    sp.add_argument('--no-cache', action='store_true', help='pykrx 파일 캐시 미사용')
    sp.add_argument('--end-date', default=None, help='pykrx 조회 기준일 YYYY-MM-DD. 미지정 시 오늘')
    sp.add_argument('--period', default='5y')
    sp.add_argument('--out', default=None)


def build_parser():
    p = argparse.ArgumentParser(description='강의 기반 차트 신호 중첩 분석기')
    p.add_argument('--config', default=None)
    sub = p.add_subparsers(dest='cmd', required=True)

    a = sub.add_parser('analyze')
    _add_provider_options(a)
    a.add_argument('--ticker', required=True)
    a.add_argument('--market', default='^KS11')
    a.add_argument('--chart', default=None)
    a.add_argument('--report', default=None, help='HTML 상세 리포트 경로')
    a.set_defaults(func=cmd_analyze)

    s = sub.add_parser('screen')
    _add_provider_options(s)
    s.add_argument('--tickers', required=True, help='한 줄에 한 종목인 txt')
    s.add_argument('--market', default='^KS11')
    s.add_argument('--max-results', type=int, default=None, help='결과 상위 N개. 미지정 시 config max_candidates')
    s.add_argument('--agent-top-n', type=int, default=30, help='서브에이전트 입력 후보 최대 개수')
    s.add_argument('--report', default=None, help='HTML 종목 랭킹 리포트 경로')
    s.set_defaults(func=cmd_screen)

    st = sub.add_parser('screen-top100', help='KOSPI_Info.xlsx 시가총액 TOP100 자동 분석')
    _add_provider_options(st, default='pykrx')
    st.add_argument('--info-excel', default=str(DEFAULT_INFO_EXCEL))
    st.add_argument('--top-n', type=int, default=100)
    st.add_argument('--sort-by', choices=['market_cap', 'trading_value', 'volume'], default='market_cap')
    st.add_argument('--include-etf', action='store_true')
    st.add_argument('--max-results', type=int, default=0, help='0이면 분석 성공 종목 전체 출력/저장')
    st.add_argument('--agent-top-n', type=int, default=30, help='서브에이전트 입력 후보 최대 개수')
    st.add_argument('--universe-out', default='output/top100_universe.csv')
    st.add_argument('--report', default='output/top100_screen.html')
    st.set_defaults(func=cmd_screen_top)

    b = sub.add_parser('backtest')
    _add_provider_options(b)
    b.add_argument('--ticker', required=True)
    b.add_argument('--min-score', type=float, default=62)
    b.add_argument('--min-technical', type=float, default=None)
    b.add_argument('--min-timing', type=float, default=None)
    b.add_argument('--max-risk', type=float, default=None)
    b.set_defaults(func=cmd_backtest)
    return p


if __name__ == '__main__':
    args = build_parser().parse_args()
    args.func(args)
