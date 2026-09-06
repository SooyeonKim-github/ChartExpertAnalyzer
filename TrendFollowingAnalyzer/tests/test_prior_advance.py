import numpy as np
import pandas as pd
from trend_following_analyzer.structure import INSUFFICIENT,RECENT_WINDOW_PROXY,SUSPECT_DATA,compute_prior_advance_snapshot

def _frame(values): return pd.DataFrame({"close":values,"ma150":np.linspace(90,110,len(values))},index=pd.bdate_range("2025-01-01",periods=len(values)))
def test_prior_advance_finds_chronological_trough_to_peak():
    values=np.r_[np.linspace(100,60,30),np.linspace(60,120,60),np.linspace(120,110,50),np.linspace(110,115,20)]; s=compute_prior_advance_snapshot(_frame(values),lookback_sessions=120,recent_window_sessions=20); assert s.status=="AVAILABLE" and s.anchor_mode==RECENT_WINDOW_PROXY and abs(s.prior_low-60)<1e-9 and abs(s.prior_peak-120)<1e-9 and abs(s.prior_advance_pct-100)<1e-9
def test_recent_proxy_window_is_excluded():
    values=np.r_[np.linspace(100,70,40),np.linspace(70,120,80),np.linspace(120,130,20)]; s=compute_prior_advance_snapshot(_frame(values),lookback_sessions=100,recent_window_sessions=20); assert s.prior_peak<130
def test_as_of_ignores_future_rows():
    f=_frame(np.linspace(100,180,180)); cutoff=f.index[150]; a=compute_prior_advance_snapshot(f,lookback_sessions=100,recent_window_sessions=20,as_of=cutoff); changed=f.copy(); changed.loc[f.index[151]:,"close"]=9999; b=compute_prior_advance_snapshot(changed,lookback_sessions=100,recent_window_sessions=20,as_of=cutoff); assert a.prior_advance_pct==b.prior_advance_pct and a.prior_peak_date==b.prior_peak_date
def test_insufficient_history_is_explicit():
    s=compute_prior_advance_snapshot(_frame(np.linspace(100,110,50)),lookback_sessions=60,recent_window_sessions=20); assert s.status==INSUFFICIENT and s.prior_advance_pct is None and s.filter_applied is False
def test_threshold_is_diagnostic_only():
    values=np.r_[np.linspace(100,80,40),np.linspace(80,130,100),np.ones(20)*125]; s=compute_prior_advance_snapshot(_frame(values),lookback_sessions=120,recent_window_sessions=20,experimental_min_advance_pct=30); assert s.experimental_min_advance_pass is True and s.filter_applied is False
def test_large_price_discontinuity_is_marked_suspect_not_filtered():
    values=np.r_[np.ones(40)*100,np.ones(60)*102,np.ones(30)*210,np.ones(20)*205]; s=compute_prior_advance_snapshot(_frame(values),lookback_sessions=120,recent_window_sessions=20); assert s.status==SUSPECT_DATA and s.filter_applied is False
