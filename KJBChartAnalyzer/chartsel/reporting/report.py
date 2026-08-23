from __future__ import annotations
from pathlib import Path
import json
import pandas as pd

def save_result_json(result, out_path: str):
    p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,'w',encoding='utf-8') as f:
        json.dump(result.to_dict(),f,ensure_ascii=False,indent=2,default=str)

def save_screen_csv(df: pd.DataFrame, out_path: str):
    p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(p,index=False,encoding='utf-8-sig')

def _meter(name, score, inverse=False):
    n=20
    effective=(100-score if inverse else score)
    filled=max(0,min(n,round(effective/100*n)))
    bar='█'*filled+'░'*(n-filled)
    return f'{name:<14} {score:5.1f}  {bar}'

def print_result(result):
    print('\n'+'='*72)
    print(f' {result.ticker} 종합 차트 분석 | {result.asof} | 종가 {result.close:,.2f}')
    print('='*72)
    print(f' 최종판단 : {result.entry_status}')
    print(f' 시장상태 : {result.market_regime} | 추격위험 : {result.chase_risk} | 위험등급 : {result.risk_level}')
    print('-'*72)
    print(_meter('Selection', result.total_score))
    print(_meter('Technical', result.technical_score))
    print(_meter('Entry Timing', result.timing_score))
    print(_meter('Risk', result.risk_score, inverse=True))
    print(_meter('Confluence', result.confluence_score))

    print('\n[종목 기술적 상태]')
    for k,v in result.technical_components.items(): print(f'  {k:<18} {v:5.1f}')
    print('\n[현재 매수 타이밍]')
    for k,v in result.timing_components.items(): print(f'  {k:<18} {v:5.1f}')

    print('\n[강점]')
    for x in result.strengths[:8]: print('  +',x)
    print('\n[위험/대기 사유]')
    if result.risks:
        for x in result.risks[:8]: print('  !',x)
    else: print('  - 뚜렷한 위험 신호 없음')

    print('\n[가격·위험관리]')
    print(f'  초기 손절 참고      {result.stop_price:,.2f}')
    print(f'  트레일링 참고       {result.trailing_stop_price:,.2f}')
    print('  지지선              '+(', '.join(f'{x:,.2f}' for x in result.support_levels[-3:]) or '-'))
    print('  저항선              '+(', '.join(f'{x:,.2f}' for x in result.resistance_levels[-3:]) or '-'))

    print('\n[분할진입 계획]')
    for x in result.entry_plan:
        print(f"  {x['step']}차 {x['fraction']*100:>3.0f}% | {x['status']:<4} | {x['trigger']}")

    print('\n[강의 신호 중첩]')
    for s in result.signals:
        print(f'  {s.category:10s} {s.score:+5.1f} | {s.reason}')
    if result.notes:
        print('\n[추가 주의]')
        for n in result.notes: print('  *',n)
