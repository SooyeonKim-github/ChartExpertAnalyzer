from pathlib import Path
import pandas as pd

from chartsel.universe.ticker_universe_service import TickerUniverseService
from chartsel.data.pykrx_provider import PykrxDataProvider, normalize_ohlcv
from chartsel.utils.date_utils import period_to_date_range


def test_universe_top100_market_cap():
    root = Path(__file__).resolve().parents[1]
    svc = TickerUniverseService(root / 'KOSPI_Info.xlsx')
    universe = svc.get_universe(top_n=100, sort_by='market_cap', include_etf=False)
    assert len(universe) == 100
    assert universe[0].ticker == '005930'
    assert universe[0].name == '삼성전자'
    assert universe[0].market == 'KOSPI'
    caps = [x.market_cap for x in universe if x.market_cap is not None]
    assert all(a >= b for a, b in zip(caps, caps[1:]))


def test_normalize_korean_ohlcv():
    idx = pd.date_range('2026-01-01', periods=3, freq='B')
    raw = pd.DataFrame({
        '시가': [1,2,3], '고가': [2,3,4], '저가': [0,1,2], '종가': [1.5,2.5,3.5], '거래량': [10,20,30]
    }, index=idx)
    out = normalize_ohlcv(raw)
    assert list(out.columns) == ['Open','High','Low','Close','Volume']
    assert float(out.iloc[-1]['Close']) == 3.5


def test_pykrx_ticker_normalize_and_period():
    assert PykrxDataProvider.normalize_ticker('005930.KS') == '005930'
    assert PykrxDataProvider.normalize_ticker('000660') == '000660'
    start, end = period_to_date_range('5y', '2026-08-22')
    assert start == '2021-08-22'
    assert end == '2026-08-22'
