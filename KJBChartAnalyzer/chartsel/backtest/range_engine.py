from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ..analysis.analyzer import ChartAnalyzer
from ..sector.sector_service import SectorBacktestService
from ..sector.sector_flow_builder import SectorFlowBuilder
from ..sector.sector_strength import sector_leader_score
from ..utils.logger import get_logger

logger = get_logger('RangeBacktester')


@dataclass(frozen=True)
class RangeBacktestParams:
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    top_n: int = 100
    sort_by: str = 'market_cap'
    forward_bars: int = 60
    history_days: int = 1200
    min_score: float = 62.0
    min_technical: float | None = None
    min_timing: float | None = None
    max_risk: float | None = None
    cooldown_bars: int = 0


def parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    raw = str(text or '').strip().replace(' ', '')
    if '~' not in raw:
        raise ValueError('기간은 YYYYMMDD~YYYYMMDD 형식으로 입력하세요. 예: 20260701~20260724')
    left, right = raw.split('~', 1)
    try:
        start = pd.to_datetime(left, format='%Y%m%d')
        end = pd.to_datetime(right, format='%Y%m%d')
    except Exception as exc:
        raise ValueError('기간은 YYYYMMDD~YYYYMMDD 형식으로 입력하세요. 예: 20260701~20260724') from exc
    if start > end:
        raise ValueError(f'시작일이 종료일보다 늦습니다: {start.date()} > {end.date()}')
    return start.normalize(), end.normalize()


def _benchmark_for_market(market: str) -> str:
    text = str(market or 'KOSPI').upper()
    return '^KQ11' if 'KOSDAQ' in text else '^KS11'


def _passes(r, params: RangeBacktestParams) -> bool:
    if r.total_score < params.min_score:
        return False
    if params.min_technical is not None and r.technical_score < params.min_technical:
        return False
    if params.min_timing is not None and r.timing_score < params.min_timing:
        return False
    if params.max_risk is not None and r.risk_score > params.max_risk:
        return False
    return True


def _forward_columns(df: pd.DataFrame, idx: int, entry: float, forward_bars: int) -> dict:
    out: dict[str, object] = {}
    available = max(0, min(forward_bars, len(df) - idx - 1))
    for h in range(1, forward_bars + 1):
        if idx + h < len(df):
            px = float(df['Close'].iloc[idx + h])
            out[f'D+{h}'] = px / entry - 1.0
        else:
            out[f'D+{h}'] = np.nan
    out['forward_available_bars'] = available
    out['forward_complete'] = bool(available >= forward_bars)
    if available:
        fwd = df.iloc[idx + 1: idx + available + 1]
        out[f'MFE_D+{forward_bars}'] = float(fwd['High'].max() / entry - 1.0)
        out[f'MAE_D+{forward_bars}'] = float(fwd['Low'].min() / entry - 1.0)
        out[f'max_close_return_D+{forward_bars}'] = float(fwd['Close'].max() / entry - 1.0)
        out[f'min_close_return_D+{forward_bars}'] = float(fwd['Close'].min() / entry - 1.0)
    else:
        out[f'MFE_D+{forward_bars}'] = np.nan
        out[f'MAE_D+{forward_bars}'] = np.nan
        out[f'max_close_return_D+{forward_bars}'] = np.nan
        out[f'min_close_return_D+{forward_bars}'] = np.nan
    return out


class RangeBacktester:
    """기간 내 각 거래일의 차트 신호를 재생하고 D+N 사후수익률을 계산한다.

    V3 추가사항
    - 현재 Universe의 종목 일봉을 한 번 캐시한 뒤 섹터별 일일 수급/가격강도를 생성한다.
    - 기존 Selection Rank, Stock Relative Strength Rank, Leader Rank는 그대로 유지한다.
    - Sector RS + Sector Flow를 결합한 Sector Composite를 별도 계산한다.
    - V3 최종 순위는 daily_sector_leader_rank로 별도 저장하므로 V2와 직접 비교 가능하다.

    주의: Universe는 현재 KOSPI_Info.xlsx 스냅샷을 고정해서 사용한다.
    따라서 과거 시점의 실제 시가총액 TOP N/과거 구성종목을 복원하는 point-in-time 백테스트는 아니다.
    """

    def __init__(self, analyzer: ChartAnalyzer, provider, universe_service):
        self.analyzer = analyzer
        self.provider = provider
        self.universe_service = universe_service
        self.last_sector_daily = pd.DataFrame()

    def _load_benchmarks(self, universe, fetch_start: str, fetch_end: str) -> dict[str, pd.DataFrame | None]:
        benchmark_cache: dict[str, pd.DataFrame | None] = {}
        for info in universe:
            benchmark = _benchmark_for_market(info.market)
            if benchmark in benchmark_cache:
                continue
            try:
                x = self.provider.get_ohlcv_by_date(benchmark, fetch_start, fetch_end)
                if x is not None and not x.empty:
                    x = x.copy()
                    x.index = pd.to_datetime(x.index).normalize()
                    x = x[~x.index.duplicated(keep='last')].sort_index()
                benchmark_cache[benchmark] = x
            except Exception as exc:
                logger.warning('%s 벤치마크 조회 실패: %s', benchmark, exc)
                benchmark_cache[benchmark] = None
        return benchmark_cache

    def _load_price_cache(self, universe, fetch_start: str, fetch_end: str, errors: list[dict]) -> dict[str, pd.DataFrame]:
        price_cache: dict[str, pd.DataFrame] = {}
        for seq, info in enumerate(universe, start=1):
            try:
                df = self.provider.get_ohlcv_by_date(info.ticker, fetch_start, fetch_end)
                if df is None or df.empty:
                    raise ValueError('OHLCV 데이터 없음')
                x = df.copy()
                x.index = pd.to_datetime(x.index).normalize()
                x = x[~x.index.duplicated(keep='last')].sort_index()
                price_cache[info.ticker] = x
            except Exception as exc:
                errors.append({'ticker': info.ticker, 'name': info.name, 'date': '', 'stage': 'load', 'error': str(exc)})
                logger.warning('[%d/%d] %s %s 데이터 조회 실패: %s', seq, len(universe), info.ticker, info.name, exc)
        return price_cache

    def _build_sector_service(
        self,
        universe,
        price_cache: dict[str, pd.DataFrame],
        benchmark_cache: dict[str, pd.DataFrame | None],
        errors: list[dict],
    ) -> SectorBacktestService | None:
        sector_cfg = self.analyzer.cfg.get('sector_strength', {}) or {}
        if not bool(sector_cfg.get('enabled', True)):
            self.last_sector_daily = pd.DataFrame()
            return None
        try:
            info_path = getattr(self.universe_service, 'info_excel_path', None)
            if info_path is None:
                raise ValueError('universe_service.info_excel_path를 찾지 못했습니다.')
            service = SectorBacktestService(info_path, sector_cfg)
            allowed = {x.ticker for x in universe if x.ticker in price_cache}
            external_price_df = None
            daily_price_dir = sector_cfg.get('daily_price_dir')
            if daily_price_dir:
                cache_dir = Path(str(daily_price_dir))
                if cache_dir.exists():
                    external_price_df = SectorFlowBuilder.load_daily_price_dir(cache_dir)
                    if not external_price_df.empty:
                        logger.info('기존 섹터 전체종목 일봉 캐시 사용 | %s | rows=%d', cache_dir, len(external_price_df))
            self.last_sector_daily = service.build(
                price_cache, benchmark_cache, allowed_tickers=allowed, external_price_df=external_price_df
            )
            logger.info(
                '섹터 컨텍스트 생성 완료 | scope=%s | rows=%d | sectors=%d',
                service.aggregation_scope, len(self.last_sector_daily), self.last_sector_daily[service.sector_col].nunique()
            )
            return service
        except Exception as exc:
            self.last_sector_daily = pd.DataFrame()
            errors.append({'ticker': '', 'name': '', 'date': '', 'stage': 'sector_build', 'error': str(exc)})
            logger.warning('섹터 강도 계산을 비활성화하고 V2 Leader로 계속 진행합니다: %s', exc)
            return None

    def run(
        self,
        params: RangeBacktestParams,
        include_etf: bool = False,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if not hasattr(self.provider, 'get_ohlcv_by_date'):
            raise ValueError('기간 백테스트는 get_ohlcv_by_date를 지원하는 provider가 필요합니다. --provider pykrx를 사용하세요.')

        universe = self.universe_service.get_universe(
            top_n=params.top_n,
            sort_by=params.sort_by,
            include_etf=include_etf,
        )
        universe_df = pd.DataFrame([{
            'source_rank': x.source_rank,
            'ticker': x.ticker,
            'name': x.name,
            'market': x.market,
            'market_cap': x.market_cap,
            'trading_value': x.trading_value,
            'volume': x.volume,
        } for x in universe])

        fetch_start = (params.start_date - pd.Timedelta(days=params.history_days)).strftime('%Y-%m-%d')
        forward_calendar_days = max(120, int(params.forward_bars * 2.0))
        fetch_end = (params.end_date + pd.Timedelta(days=forward_calendar_days)).strftime('%Y-%m-%d')

        rows: list[dict] = []
        errors: list[dict] = []
        benchmark_cache = self._load_benchmarks(universe, fetch_start, fetch_end)
        price_cache = self._load_price_cache(universe, fetch_start, fetch_end, errors)
        sector_service = self._build_sector_service(universe, price_cache, benchmark_cache, errors)

        # universe 결과에도 업종을 남겨 이후 검증하기 쉽게 한다.
        if sector_service is not None and not sector_service.sector_map_df.empty and not universe_df.empty:
            sm = sector_service.sector_map_df[['Ticker', sector_service.sector_col]].rename(
                columns={'Ticker': 'ticker', sector_service.sector_col: 'sector_name'}
            )
            universe_df = universe_df.merge(sm, on='ticker', how='left')

        min_hist = max(self.analyzer.cfg['moving_average']['long'] + 10, 140)
        sector_cfg = self.analyzer.cfg.get('sector_strength', {}) or {}
        true_leader_selection = float(sector_cfg.get('true_leader_min_selection', 70.0))
        true_leader_stock_rs = float(sector_cfg.get('true_leader_min_stock_rs', 70.0))
        true_leader_sector = float(sector_cfg.get('true_leader_min_sector', 70.0))

        for seq, info in enumerate(universe, start=1):
            ticker = info.ticker
            benchmark = _benchmark_for_market(info.market)
            df = price_cache.get(ticker)
            if df is None or df.empty:
                continue
            market_df = benchmark_cache.get(benchmark)
            try:
                signal_positions = np.flatnonzero(
                    (df.index.normalize() >= params.start_date) &
                    (df.index.normalize() <= params.end_date)
                )
                if len(signal_positions) == 0:
                    raise ValueError('입력 기간 내 거래일 없음')

                last_signal_idx: int | None = None
                signal_count = 0
                for idx in signal_positions:
                    idx = int(idx)
                    if idx < min_hist - 1:
                        continue
                    if params.cooldown_bars > 0 and last_signal_idx is not None and idx - last_signal_idx <= params.cooldown_bars:
                        continue
                    sub = df.iloc[:idx + 1]
                    if market_df is not None and not market_df.empty:
                        market_sub = market_df.loc[market_df.index <= df.index[idx]]
                    else:
                        market_sub = None
                    try:
                        r = self.analyzer.analyze(ticker, sub, market_sub)
                    except Exception as exc:
                        errors.append({
                            'ticker': ticker, 'name': info.name,
                            'date': str(df.index[idx].date()), 'stage': 'analyze', 'error': str(exc),
                        })
                        continue
                    if not _passes(r, params):
                        continue

                    signal_date = pd.Timestamp(df.index[idx]).normalize()
                    if sector_service is not None:
                        sctx = sector_service.context(ticker, signal_date, fallback_market=info.market)
                    else:
                        sctx = {
                            'sector_name': '기타/미분류', 'sector_rs_score': np.nan,
                            'sector_composite_score': np.nan, 'sector_rs_rank': np.nan,
                            'sector_composite_rank': np.nan, 'sector_flow_score': np.nan,
                            'sector_flow_score_100': np.nan, 'sector_flow_rank': np.nan,
                            'sector_flow_label': '', 'sector_rs_available': False, 'sector_flow_available': False, 'sector_aggregation_scope': 'none',
                        }

                    sector_score = sctx.get('sector_composite_score')
                    if sector_score is None or not np.isfinite(float(sector_score)):
                        sector_score_for_leader = None
                    else:
                        sector_score_for_leader = float(sector_score)
                    v3_leader, v3_weights = sector_leader_score(
                        r.total_score,
                        r.relative_strength_score,
                        sector_score_for_leader,
                        r.market_regime,
                        sector_cfg,
                    )
                    is_true_leader = bool(
                        r.total_score >= true_leader_selection
                        and r.relative_strength_score >= true_leader_stock_rs
                        and sector_score_for_leader is not None
                        and sector_score_for_leader >= true_leader_sector
                    )

                    entry = float(df['Close'].iloc[idx])
                    row = {
                        'signal_date': signal_date,
                        'ticker': ticker,
                        'name': info.name,
                        'market': info.market,
                        'sector_name': sctx.get('sector_name', '기타/미분류'),
                        'source_rank': info.source_rank,
                        'market_cap': info.market_cap,
                        'entry_close': entry,
                        'selection_score': r.total_score,
                        'selection_grade': r.grade,
                        'technical_score': r.technical_score,
                        'technical_grade': r.technical_grade,
                        'timing_score': r.timing_score,
                        'timing_grade': r.timing_grade,
                        'risk_score': r.risk_score,
                        'risk_level': r.risk_level,
                        'confluence_score': r.confluence_score,
                        'relative_strength_score': r.relative_strength_score,
                        'relative_strength_grade': r.relative_strength_grade,
                        # V2: Selection + Stock RS
                        'leader_score': r.leader_score,
                        'relative_strength_weight': r.relative_strength_weight,
                        # V3: Selection + Stock RS + Sector Composite
                        'sector_leader_score': v3_leader,
                        'sector_leader_selection_weight': v3_weights['selection'],
                        'sector_leader_stock_rs_weight': v3_weights['stock_rs'],
                        'sector_leader_sector_weight': v3_weights['sector'],
                        'is_true_leader': is_true_leader,
                        'rs_rel_return_5d': r.relative_strength_metrics.get('relative_return_5d'),
                        'rs_rel_return_20d': r.relative_strength_metrics.get('relative_return_20d'),
                        'rs_rel_return_60d': r.relative_strength_metrics.get('relative_return_60d'),
                        'rs_down_day_hit_rate_20d': r.relative_strength_metrics.get('down_day_hit_rate_20d'),
                        'rs_down_day_avg_excess_20d': r.relative_strength_metrics.get('down_day_avg_excess_20d'),
                        'rs_drawdown_advantage_60d': r.relative_strength_metrics.get('drawdown_advantage_60d'),
                        'rs_rebound_advantage_60d': r.relative_strength_metrics.get('rebound_advantage_60d'),
                        'sector_rs_score': sctx.get('sector_rs_score'),
                        'sector_rs_available': sctx.get('sector_rs_available', False),
                        'sector_rs_rank': sctx.get('sector_rs_rank'),
                        'sector_composite_score': sctx.get('sector_composite_score'),
                        'sector_composite_rank': sctx.get('sector_composite_rank'),
                        'sector_flow_score': sctx.get('sector_flow_score'),
                        'sector_flow_score_100': sctx.get('sector_flow_score_100'),
                        'sector_flow_available': sctx.get('sector_flow_available', False),
                        'sector_flow_rank': sctx.get('sector_flow_rank'),
                        'sector_flow_label': sctx.get('sector_flow_label'),
                        'sector_aggregation_scope': sctx.get('sector_aggregation_scope'),
                        'sector_rel_return_5d': sctx.get('sector_rel_return_5d'),
                        'sector_rel_return_20d': sctx.get('sector_rel_return_20d'),
                        'sector_rel_return_60d': sctx.get('sector_rel_return_60d'),
                        'sector_down_day_hit_rate_20d': sctx.get('sector_down_day_hit_rate_20d'),
                        'sector_drawdown_advantage_60d': sctx.get('sector_drawdown_advantage_60d'),
                        'sector_rebound_advantage_60d': sctx.get('sector_rebound_advantage_60d'),
                        'sector_tv_ratio_20': sctx.get('sector_tv_ratio_20'),
                        'sector_relative_tv_strength_20': sctx.get('sector_relative_tv_strength_20'),
                        'sector_rising_ratio': sctx.get('sector_rising_ratio'),
                        'entry_status': r.entry_status,
                        'chase_risk': r.chase_risk,
                        'market_regime': r.market_regime,
                        'stop_price': r.stop_price,
                        'trailing_stop_price': r.trailing_stop_price,
                        'bullish_signals': sum(1 for s in r.signals if s.score > 0),
                        'bearish_signals': sum(1 for s in r.signals if s.score < 0),
                        'top_strengths': ' | '.join(r.strengths[:3]),
                        'top_risks': ' | '.join(r.risks[:3]),
                    }
                    row.update(_forward_columns(df, idx, entry, params.forward_bars))
                    rows.append(row)
                    signal_count += 1
                    last_signal_idx = idx

                logger.info('[%d/%d] %s %s 완료 | 기간내 신호 %d건', seq, len(universe), ticker, info.name, signal_count)
            except Exception as exc:
                errors.append({'ticker': ticker, 'name': info.name, 'date': '', 'stage': 'signal_range', 'error': str(exc)})
                logger.warning('[%d/%d] %s %s 실패: %s', seq, len(universe), ticker, info.name, exc)

        events = pd.DataFrame(rows)
        if not events.empty:
            events['daily_rank'] = events.groupby('signal_date')['selection_score'].rank(method='first', ascending=False).astype(int)
            events['daily_strength_rank'] = events.groupby('signal_date')['relative_strength_score'].rank(method='first', ascending=False).astype(int)
            events['daily_leader_rank'] = events.groupby('signal_date')['leader_score'].rank(method='first', ascending=False).astype(int)
            events['daily_sector_leader_rank'] = events.groupby('signal_date')['sector_leader_score'].rank(method='first', ascending=False).astype(int)
            events['sector_stock_rs_rank'] = events.groupby(['signal_date', 'sector_name'])['relative_strength_score'].rank(method='first', ascending=False).astype(int)
            events['sector_stock_leader_rank'] = events.groupby(['signal_date', 'sector_name'])['sector_leader_score'].rank(method='first', ascending=False).astype(int)

            front = [
                'signal_date', 'daily_rank', 'daily_strength_rank', 'daily_leader_rank', 'daily_sector_leader_rank',
                'sector_stock_rs_rank', 'sector_stock_leader_rank',
                'ticker', 'name', 'market', 'sector_name', 'source_rank', 'market_cap', 'entry_close',
                'selection_score', 'selection_grade', 'technical_score', 'technical_grade', 'timing_score', 'timing_grade',
                'risk_score', 'risk_level', 'confluence_score',
                'relative_strength_score', 'relative_strength_grade', 'leader_score', 'relative_strength_weight',
                'sector_leader_score', 'sector_leader_selection_weight', 'sector_leader_stock_rs_weight', 'sector_leader_sector_weight', 'is_true_leader',
                'sector_rs_score', 'sector_rs_available', 'sector_rs_rank', 'sector_composite_score', 'sector_composite_rank',
                'sector_flow_score', 'sector_flow_score_100', 'sector_flow_available', 'sector_flow_rank', 'sector_flow_label', 'sector_aggregation_scope',
                'rs_rel_return_5d', 'rs_rel_return_20d', 'rs_rel_return_60d', 'rs_down_day_hit_rate_20d', 'rs_down_day_avg_excess_20d',
                'rs_drawdown_advantage_60d', 'rs_rebound_advantage_60d',
                'sector_rel_return_5d', 'sector_rel_return_20d', 'sector_rel_return_60d', 'sector_down_day_hit_rate_20d',
                'sector_drawdown_advantage_60d', 'sector_rebound_advantage_60d', 'sector_tv_ratio_20',
                'sector_relative_tv_strength_20', 'sector_rising_ratio',
                'entry_status', 'chase_risk', 'market_regime', 'stop_price', 'trailing_stop_price',
                'bullish_signals', 'bearish_signals', 'top_strengths', 'top_risks',
                'forward_available_bars', 'forward_complete', f'MFE_D+{params.forward_bars}', f'MAE_D+{params.forward_bars}',
                f'max_close_return_D+{params.forward_bars}', f'min_close_return_D+{params.forward_bars}',
            ]
            return_cols = [f'D+{h}' for h in range(1, params.forward_bars + 1)]
            events = events[[c for c in front if c in events.columns] + return_cols]
            events = events.sort_values(
                ['signal_date', 'daily_sector_leader_rank', 'sector_leader_score'],
                ascending=[True, True, False],
            ).reset_index(drop=True)

        summary = build_forward_summary(events, params.forward_bars)
        errors_df = pd.DataFrame(errors)
        return events, summary, universe_df, errors_df


def build_forward_summary(events: pd.DataFrame, forward_bars: int = 60) -> pd.DataFrame:
    rows: list[dict] = []
    if events.empty:
        return pd.DataFrame(columns=['horizon', 'valid_count', 'avg_return', 'median_return', 'win_rate', 'loss_rate', 'std_return'])
    for h in range(1, forward_bars + 1):
        c = f'D+{h}'
        s = pd.to_numeric(events[c], errors='coerce').dropna()
        rows.append({
            'horizon': c,
            'trading_days': h,
            'valid_count': int(s.size),
            'avg_return': float(s.mean()) if len(s) else np.nan,
            'median_return': float(s.median()) if len(s) else np.nan,
            'win_rate': float((s > 0).mean()) if len(s) else np.nan,
            'loss_rate': float((s < 0).mean()) if len(s) else np.nan,
            'std_return': float(s.std(ddof=0)) if len(s) else np.nan,
            'best_return': float(s.max()) if len(s) else np.nan,
            'worst_return': float(s.min()) if len(s) else np.nan,
        })
    return pd.DataFrame(rows)


def key_horizon_summary(summary: pd.DataFrame, horizons: Iterable[int] = (1, 5, 10, 20, 40, 60)) -> pd.DataFrame:
    wanted = {f'D+{int(h)}' for h in horizons}
    if summary.empty:
        return summary.copy()
    return summary[summary['horizon'].isin(wanted)].copy().reset_index(drop=True)
