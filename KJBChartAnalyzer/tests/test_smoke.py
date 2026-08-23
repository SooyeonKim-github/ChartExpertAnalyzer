import numpy as np
import pandas as pd
from pathlib import Path
from chartsel.config import load_config
from chartsel.analysis.analyzer import ChartAnalyzer
from chartsel.reporting.html_report import save_analysis_html


def make_df(n=320):
    idx=pd.date_range('2025-01-01',periods=n,freq='B')
    base=np.linspace(100,180,n)+np.sin(np.arange(n)/9)*4
    close=pd.Series(base,index=idx)
    return pd.DataFrame({
        'Open':close.shift(1).fillna(close.iloc[0]),
        'High':close+2,
        'Low':close-2,
        'Close':close,
        'Volume':np.linspace(100000,160000,n)
    },index=idx)


def test_analyzer_runs(tmp_path):
    cfg=load_config()
    r=ChartAnalyzer(cfg).analyze('TEST',make_df())
    assert 0 <= r.total_score <= 100
    assert 0 <= r.technical_score <= 100
    assert 0 <= r.timing_score <= 100
    assert 0 <= r.risk_score <= 100
    assert len(r.signals) == 7
    assert len(r.entry_plan) == 5
    out=tmp_path/'report.html'
    save_analysis_html(r,str(out))
    assert out.exists()
    assert 'Technical' in out.read_text(encoding='utf-8')
