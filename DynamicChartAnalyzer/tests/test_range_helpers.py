import pandas as pd

from main_range import _get_universe, _latest_market_date


class CalendarStock:
    def get_market_ohlcv_by_date(self, start, end, ticker, adjusted=True):
        assert ticker == "005930"
        return pd.DataFrame(
            {"종가": [70000, 70500]},
            index=pd.to_datetime(["2026-08-27", "2026-08-28"]),
        )

    def get_market_ohlcv_by_ticker(self, date, market="KOSPI"):
        raise AssertionError("calendar fallback should not be needed")


class UniverseStock:
    def get_market_ohlcv_by_ticker(self, date, market="KOSPI"):
        if market == "KOSPI":
            return pd.DataFrame(
                {
                    "종가": [100, 200],
                    "거래량": [1000, 2000],
                    "거래대금": [100000, 400000],
                    "시가총액": [1_000_000, 3_000_000],
                },
                index=["000001", "000002"],
            )
        if market == "KOSDAQ":
            return pd.DataFrame(
                {
                    "종가": [300],
                    "거래량": [500],
                    "거래대금": [150000],
                    "시가총액": [2_000_000],
                },
                index=["000003"],
            )
        raise AssertionError(market)

    def get_market_cap_by_ticker(self, date, market="KOSPI"):
        raise RuntimeError("dedicated cap endpoint unavailable")

    def get_market_ticker_name(self, ticker):
        return f"N{ticker}"


def test_latest_market_date_uses_daily_calendar():
    assert _latest_market_date(CalendarStock(), pd.Timestamp("2026-08-31")) == "20260828"


def test_universe_can_use_ohlcv_snapshot_market_cap(monkeypatch):
    monkeypatch.setattr("main_range._import_pykrx", lambda: UniverseStock())
    out = _get_universe("20260828", top_n=2, sort_by="market_cap")
    assert out["ticker"].tolist() == ["000002", "000003"]
    assert out["source_rank"].tolist() == [1, 2]
