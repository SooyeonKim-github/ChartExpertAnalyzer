from __future__ import annotations

import numpy as np
import pandas as pd

from config import DEFAULT_CONFIG
from core.pivots import find_confirmed_pivots
from core.channel_analyzer import build_best_rising_channel


def synthetic_channel(n=180):
    idx=pd.bdate_range("2025-01-01",periods=n)
    t=np.arange(n)
    base=100+t*0.22
    cycle=8*np.sin(t/8.0)
    close=base+cycle
    # 마지막 구간을 하단 눌림 후 반등 형태로 만든다.
    close[-15:]=np.array([130,128,126,124,122,121,122,121.5,122.5,124,126,128,129,130,131])
    open_=close*(1+0.002*np.sin(t))
    high=np.maximum(open_,close)+1.2
    low=np.minimum(open_,close)-1.2
    vol=np.full(n,100000.0)
    vol[-10]=260000
    return pd.DataFrame({"Open":open_,"High":high,"Low":low,"Close":close,"Volume":vol},index=idx)


def test_pivots_confirmed_without_using_unfinished_tail():
    df=synthetic_channel()
    highs,lows=find_confirmed_pivots(df,3)
    assert all(p.pos <= len(df)-4 for p in highs+lows)


def test_rising_channel_can_be_built_on_clean_uptrend():
    df=synthetic_channel()
    highs,lows=find_confirmed_pivots(df,3)
    ch=build_best_rising_channel(df,highs,lows,DEFAULT_CONFIG)
    assert ch is not None
    assert ch.slope > 0

from core.backtester import evaluate_forward_returns


def test_forward_returns_are_trading_bar_based_and_exact():
    idx = pd.bdate_range("2026-01-02", periods=25)
    close = np.arange(100.0, 125.0)
    df = pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(len(idx), 1000.0),
        },
        index=idx,
    )
    perf = evaluate_forward_returns(df, 0, 20)
    assert perf["Forward_Complete_20D"] == 1
    assert perf["D+1_Date"] == idx[1].strftime("%Y-%m-%d")
    assert perf["D+20_Date"] == idx[20].strftime("%Y-%m-%d")
    assert perf["D+1_Close_Return_Pct"] == 1.0
    assert perf["D+20_Close_Return_Pct"] == 20.0
    assert perf["MFE_20D_Pct"] == 21.0
    assert perf["MAE_20D_Pct"] == 0.0


def test_forward_returns_leave_missing_future_bars_blank():
    idx = pd.bdate_range("2026-01-02", periods=6)
    close = np.arange(100.0, 106.0)
    df = pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(len(idx), 1000.0),
        },
        index=idx,
    )
    perf = evaluate_forward_returns(df, 0, 20)
    assert perf["Forward_Available_Bars"] == 5
    assert perf["Forward_Complete_20D"] == 0
    assert pd.isna(perf["D+20_Close_Return_Pct"])
