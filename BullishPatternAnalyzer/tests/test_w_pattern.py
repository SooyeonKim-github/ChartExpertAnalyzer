import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from core.indicators import add_indicators
from patterns.reversal import WPatternDetector


def test_w_pattern_detector_handles_synthetic_w_without_crashing():
    n=120; close=np.linspace(100,110,n); close[55:66]=np.linspace(105,90,11); close[66:76]=np.linspace(90,101,10); close[76:88]=np.linspace(101,93,12); close[88:]=np.linspace(93,106,n-88); volume=np.full(n,1000.0); volume[55:66]=1800; volume[76:88]=900; idx=pd.bdate_range("2026-01-01",periods=n); raw=pd.DataFrame({"open":close*0.997,"high":close*1.01,"low":close*0.99,"close":close,"volume":volume},index=idx); result=WPatternDetector().detect(add_indicators(raw)); assert result is None or result.pattern_type.value=="W_PATTERN"
