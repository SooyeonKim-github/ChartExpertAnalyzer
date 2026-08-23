from __future__ import annotations

import pandas as pd

from ..analysis.analyzer import ChartAnalyzer
from ..utils.logger import get_logger

logger = get_logger('StockSelector')


def _benchmark_for_market(market: str) -> str:
    text = str(market or 'KOSPI').upper()
    return '^KQ11' if 'KOSDAQ' in text else '^KS11'


class StockSelector:
    def __init__(self, analyzer: ChartAnalyzer, provider, cfg: dict):
        self.analyzer = analyzer
        self.provider = provider
        self.cfg = cfg

    @staticmethod
    def _row_from_result(r, meta=None) -> dict:
        row = {
            'ticker': r.ticker, 'asof': r.asof, 'close': r.close,
            'score': r.total_score, 'grade': r.grade,
            'technical_score': r.technical_score, 'technical_grade': r.technical_grade,
            'timing_score': r.timing_score, 'timing_grade': r.timing_grade,
            'risk_score': r.risk_score, 'risk_level': r.risk_level,
            'confluence_score': r.confluence_score, 'chase_risk': r.chase_risk,
            'relative_strength_score': r.relative_strength_score, 'relative_strength_grade': r.relative_strength_grade,
            'leader_score': r.leader_score, 'relative_strength_weight': r.relative_strength_weight,
            'action': r.entry_status, 'market_regime': r.market_regime,
            'stop_price': r.stop_price, 'trailing_stop': r.trailing_stop_price,
            'bullish_signals': sum(1 for s in r.signals if s.score > 0),
            'bearish_signals': sum(1 for s in r.signals if s.score < 0),
            'top_strengths': ' | '.join(r.strengths[:3]),
            'top_risks': ' | '.join(r.risks[:3]),
        }
        if meta is not None:
            row.update({
                'name': getattr(meta, 'name', ''),
                'market': getattr(meta, 'market', ''),
                'market_cap': getattr(meta, 'market_cap', None),
                'trading_value': getattr(meta, 'trading_value', None),
                'volume_universe': getattr(meta, 'volume', None),
                'source_rank': getattr(meta, 'source_rank', None),
            })
        return row

    def _finish(self, rows: list[dict], limit: int | None = None) -> pd.DataFrame:
        table = pd.DataFrame(rows)
        if table.empty:
            return table
        table = table.sort_values(
            ['leader_score', 'score', 'timing_score', 'technical_score', 'risk_score'],
            ascending=[False, False, False, False, True],
        )
        if limit is None:
            limit = int(self.cfg['selection']['max_candidates'])
        if limit and limit > 0:
            table = table.head(limit)
        return table.reset_index(drop=True)

    def screen(self, tickers: list[str], period: str = '2y', market_ticker: str | None = None, limit: int | None = None) -> tuple[pd.DataFrame, list]:
        market_df = None
        if market_ticker:
            try:
                market_df = self.provider.get_ohlcv(market_ticker, period=period)
            except Exception as exc:
                logger.warning('시장 데이터 조회 실패 %s: %s', market_ticker, exc)
        rows = []
        errors = []
        for ticker in tickers:
            try:
                df = self.provider.get_ohlcv(ticker, period=period)
                r = self.analyzer.analyze(ticker, df, market_df)
                rows.append(self._row_from_result(r))
            except Exception as exc:
                errors.append((ticker, str(exc)))
        return self._finish(rows, limit), errors

    def screen_universe(self, universe, period: str = '5y', limit: int | None = 0) -> tuple[pd.DataFrame, list]:
        """TickerInfo 목록을 분석한다. KOSPI/KOSDAQ별 벤치마크를 각각 한 번만 조회해 재사용한다."""
        market_cache: dict[str, pd.DataFrame | None] = {}
        rows: list[dict] = []
        errors: list[tuple[str, str]] = []

        for idx, info in enumerate(universe, start=1):
            ticker = info.ticker
            benchmark = _benchmark_for_market(info.market)
            if benchmark not in market_cache:
                try:
                    market_cache[benchmark] = self.provider.get_ohlcv(benchmark, period=period)
                except Exception as exc:
                    logger.warning('%s 벤치마크 조회 실패: %s', benchmark, exc)
                    market_cache[benchmark] = None
            try:
                data_ticker = ticker
                if self.provider.__class__.__name__ == 'YFinanceProvider':
                    data_ticker = f"{ticker}.KQ" if 'KOSDAQ' in str(info.market).upper() else f"{ticker}.KS"
                df = self.provider.get_ohlcv(data_ticker, period=period)
                r = self.analyzer.analyze(data_ticker, df, market_cache[benchmark])
                row = self._row_from_result(r, info)
                row['data_ticker'] = data_ticker
                row['ticker'] = ticker
                rows.append(row)
                logger.info('[%d/%d] %s %s 분석 완료 | Selection %.1f', idx, len(universe), ticker, info.name, r.total_score)
            except Exception as exc:
                errors.append((ticker, str(exc)))
                logger.warning('[%d/%d] %s %s 분석 실패: %s', idx, len(universe), ticker, info.name, exc)

        return self._finish(rows, limit), errors
