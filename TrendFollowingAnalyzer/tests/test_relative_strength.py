import numpy as np
import pandas as pd
from trend_following_analyzer.strength import RS_INSUFFICIENT, WEAK_MARKET_RESILIENT, add_cross_sectional_rs_percentiles, compute_relative_strength_snapshot

def _frame(values,start="2026-01-01"):
    return pd.DataFrame({"close":values},index=pd.bdate_range(start,periods=len(values)))

def test_market_weak_stock_resilient_has_positive_rs():
    snap=compute_relative_strength_snapshot(_frame(np.linspace(100,140,80)),_frame(np.linspace(100,95,80)),market="KOSPI"); assert snap.rs_20d_pct>0 and snap.rs_60d_pct>0 and snap.rs_label==WEAK_MARKET_RESILIENT

def test_relative_strength_uses_price_ratio_not_simple_difference():
    stock=_frame(np.linspace(100,120,80)); benchmark=_frame(np.linspace(100,110,80)); snap=compute_relative_strength_snapshot(stock,benchmark,market="KOSPI"); expected=((stock["close"].iloc[-1]/stock["close"].iloc[-21])/(benchmark["close"].iloc[-1]/benchmark["close"].iloc[-21])-1)*100; assert abs(snap.rs_20d_pct-expected)<1e-12

def test_insufficient_history_is_explicit():
    snap=compute_relative_strength_snapshot(_frame(np.linspace(100,110,40)),_frame(np.linspace(100,105,40)),market="KOSPI"); assert snap.status==RS_INSUFFICIENT and snap.rs_60d_pct is None

def test_future_rows_are_ignored_with_as_of():
    idx=pd.bdate_range("2026-01-01",periods=90); stock=pd.DataFrame({"close":np.linspace(100,130,90)},index=idx); benchmark=pd.DataFrame({"close":np.linspace(100,105,90)},index=idx); cutoff=idx[70]; first=compute_relative_strength_snapshot(stock,benchmark,market="KOSPI",as_of=cutoff); stock.loc[idx[71]:,"close"]=9999; benchmark.loc[idx[71]:,"close"]=1; second=compute_relative_strength_snapshot(stock,benchmark,market="KOSPI",as_of=cutoff); assert first.rs_20d_pct==second.rs_20d_pct and first.rs_60d_pct==second.rs_60d_pct

def test_cross_sectional_percentiles_rank_stronger_stock_higher():
    frame=pd.DataFrame({"ticker":["A","B","C"],"market":["KOSPI"]*3,"rs_20d_pct":[10.,5.,-1.],"rs_60d_pct":[20.,3.,-2.]}); ranked=add_cross_sectional_rs_percentiles(frame).set_index("ticker"); assert ranked.loc["A","rs_percentile_composite"]>ranked.loc["B","rs_percentile_composite"]>ranked.loc["C","rs_percentile_composite"]
