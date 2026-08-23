from __future__ import annotations
import pandas as pd
from ..analysis.analyzer import ChartAnalyzer

class SimpleBacktester:
    """강의 규칙 점수의 사후 검증용. 미래를 예측하는 모델이 아니라 신호 이후 수익률 통계를 확인한다."""
    def __init__(self, analyzer: ChartAnalyzer):
        self.analyzer=analyzer

    def event_study(self, ticker: str, df: pd.DataFrame, horizons=(5,20,60), min_score=62,
                    min_technical: float | None=None, min_timing: float | None=None,
                    max_risk: float | None=None) -> pd.DataFrame:
        rows=[]
        min_hist=max(self.analyzer.cfg['moving_average']['long']+10,140)
        for i in range(min_hist, len(df)-max(horizons)):
            sub=df.iloc[:i+1]
            try:
                r=self.analyzer.analyze(ticker,sub)
            except Exception:
                continue
            if r.total_score < min_score: continue
            if min_technical is not None and r.technical_score < min_technical: continue
            if min_timing is not None and r.timing_score < min_timing: continue
            if max_risk is not None and r.risk_score > max_risk: continue
            entry=float(df['Close'].iloc[i])
            row={
                'date':df.index[i], 'score':r.total_score,
                'technical_score':r.technical_score,'timing_score':r.timing_score,
                'risk_score':r.risk_score,'confluence_score':r.confluence_score,
                'entry_status':r.entry_status,'entry':entry
            }
            for h in horizons:
                exitp=float(df['Close'].iloc[i+h])
                row[f'ret_{h}d']=exitp/entry-1
            rows.append(row)
        return pd.DataFrame(rows)
