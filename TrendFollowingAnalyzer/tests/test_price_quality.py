from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from MarketData.quality import QUALITY_OK,QUALITY_SUSPECT,assess_price_quality

def _frame(values): return pd.DataFrame({"close":values},index=pd.bdate_range("2026-01-02",periods=len(values)))
def test_quality_accepts_continuous_adjusted_history():
    s=assess_price_quality(_frame([100,105,102,110,108])); assert s.status==QUALITY_OK and s.large_jump_count==0
def test_quality_flags_large_discontinuity():
    s=assess_price_quality(_frame([100,103,200,202,205]),jump_threshold_pct=35); assert s.status==QUALITY_SUSPECT and s.large_jump_count==1 and s.max_abs_daily_return_pct>90
