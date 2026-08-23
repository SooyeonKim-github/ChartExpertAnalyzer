from __future__ import annotations
from pathlib import Path
from html import escape
import math
import pandas as pd


def _fmt(v, digits=1):
    if v is None:
        return '-'
    try:
        if math.isnan(float(v)):
            return '-'
    except Exception:
        pass
    try:
        return f'{float(v):,.{digits}f}'
    except Exception:
        return escape(str(v))


def _badge(text: str, kind: str='neutral') -> str:
    return f'<span class="badge {kind}">{escape(str(text))}</span>'


def _score_class(score: float, inverse: bool=False) -> str:
    if inverse:
        return 'good' if score < 40 else 'warn' if score < 65 else 'bad'
    return 'good' if score >= 72 else 'warn' if score >= 55 else 'bad'


def _bar(label: str, value: float, max_value: float) -> str:
    pct=max(0,min(100,(value/max_value*100 if max_value else 0)))
    return f'''<div class="metric-row"><div>{escape(label)}</div><div class="bar"><i style="width:{pct:.1f}%"></i></div><strong>{value:.1f}/{max_value:g}</strong></div>'''


def _base_css() -> str:
    return '''
    :root{--bg:#f5f7fb;--card:#fff;--text:#172033;--muted:#6b7280;--line:#e5e7eb;--good:#137a54;--goodbg:#e9f8f1;--warn:#a05a00;--warnbg:#fff4df;--bad:#b42318;--badbg:#fff0ee;--accent:#3257d5}
    *{box-sizing:border-box} body{margin:0;background:var(--bg);font-family:Arial,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;color:var(--text)}
    .wrap{max-width:1240px;margin:0 auto;padding:28px 20px 56px}.top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:18px}
    h1{font-size:28px;margin:0 0 6px}.sub{color:var(--muted);font-size:14px}.hero-action{font-size:18px;font-weight:700;padding:10px 15px;border-radius:12px;background:#eef2ff;color:#273b91}
    .grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:16px 0}.score-card,.card{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 3px 14px rgba(15,23,42,.04)}
    .score-card{padding:16px}.score-label{color:var(--muted);font-size:12px}.score{font-size:30px;font-weight:800;margin-top:4px}.good .score{color:var(--good)}.warn .score{color:var(--warn)}.bad .score{color:var(--bad)}
    .card{padding:18px;margin-top:14px}.card h2{font-size:18px;margin:0 0 14px}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
    .badge{display:inline-block;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700;margin:2px}.badge.good{background:var(--goodbg);color:var(--good)}.badge.warn{background:var(--warnbg);color:var(--warn)}.badge.bad{background:var(--badbg);color:var(--bad)}.badge.neutral{background:#eef1f5;color:#4b5563}
    ul{margin:0;padding-left:20px}li{margin:7px 0}.metric-row{display:grid;grid-template-columns:155px 1fr 72px;gap:10px;align-items:center;margin:10px 0;font-size:13px}.bar{height:9px;background:#edf0f5;border-radius:6px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);border-radius:6px}
    table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:9px 8px;text-align:left}th{color:#4b5563;background:#fafbfc;position:sticky;top:0}.num{text-align:right;font-variant-numeric:tabular-nums}.chart{width:100%;border-radius:12px;border:1px solid var(--line)}
    .kv{display:grid;grid-template-columns:130px 1fr;gap:7px 12px;font-size:14px}.kv b{color:#4b5563}.notice{font-size:12px;color:var(--muted);line-height:1.55}.summary{font-size:16px;line-height:1.65;background:#f8faff;border-left:4px solid var(--accent);padding:14px 16px;border-radius:8px}
    .toolbar{display:flex;gap:10px;margin:12px 0}.toolbar input{padding:9px 12px;border:1px solid var(--line);border-radius:10px;min-width:260px;background:#fff}
    @media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.two,.three{grid-template-columns:1fr}.top{display:block}.hero-action{margin-top:10px;display:inline-block}.metric-row{grid-template-columns:120px 1fr 60px}}
    '''


def save_analysis_html(result, out_path: str, chart_path: str | None=None):
    p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True)
    chart_html=''
    if chart_path:
        cp=Path(chart_path)
        try: rel=cp.relative_to(p.parent)
        except Exception: rel=Path(cp.name)
        chart_html=f'<div class="card"><h2>차트</h2><img class="chart" src="{escape(str(rel).replace(chr(92), "/"))}" alt="analysis chart"></div>'

    scores=[
        ('Selection',result.total_score,False),('Technical',result.technical_score,False),('Timing',result.timing_score,False),('Risk',result.risk_score,True),('Confluence',result.confluence_score,False)
    ]
    score_cards=''.join(f'<div class="score-card {_score_class(v,inv)}"><div class="score-label">{name}</div><div class="score">{v:.1f}</div></div>' for name,v,inv in scores)

    tech_max={'일봉 추세':30,'주봉 교차검증':15,'고저점 구조':25,'지지·저항 구조':20,'패턴·밴드 추세':10}
    time_max={'가격 위치':30,'이평선·추격 위험':25,'캔들·거래량':25,'볼린저·시장':20}
    tech_bars=''.join(_bar(k,v,tech_max.get(k,100)) for k,v in result.technical_components.items())
    time_bars=''.join(_bar(k,v,time_max.get(k,100)) for k,v in result.timing_components.items())

    strengths=''.join(f'<li>{escape(x)}</li>' for x in result.strengths) or '<li>뚜렷한 우위 신호 없음</li>'
    risks=''.join(f'<li>{escape(x)}</li>' for x in result.risks) or '<li>뚜렷한 위험 신호 없음</li>'
    notes=''.join(f'<li>{escape(x)}</li>' for x in result.notes) or '<li>추가 주의사항 없음</li>'

    plan_rows=''.join(
        f'<tr><td>{x["step"]}차</td><td class="num">{x["fraction"]*100:.0f}%</td><td>{escape(x["trigger"])}</td><td>{_badge(x["status"], "good" if x["status"]=="충족" else "warn" if x["status"] in ("조건부","대기") else "bad")}</td></tr>'
        for x in result.entry_plan
    )
    signal_rows=''.join(
        f'<tr><td>{escape(s.category)}</td><td>{escape(s.name)}</td><td class="num">{s.score:+.1f}</td><td>{escape(s.reason)}</td></tr>' for s in result.signals
    )
    supports=', '.join(_fmt(x,2) for x in result.support_levels[-5:]) or '-'
    resistances=', '.join(_fmt(x,2) for x in result.resistance_levels[-5:]) or '-'

    if result.entry_status.startswith('분할진입'):
        summary='중기 차트 구조와 현재 진입 위치가 모두 양호합니다. 한 번에 진입하기보다 강의의 피라미딩 원칙대로 확인 신호마다 비중을 나누는 구간입니다.'
    elif '눌림목' in result.entry_status:
        summary='종목의 기술적 상태는 좋지만 현재 가격의 이격·단기 상승 부담이 있습니다. 추격보다 MA5~MA20 또는 돌파 지지선 부근 눌림목 확인이 우선입니다.'
    elif '돌파' in result.entry_status:
        summary='기술적 구조는 양호하지만 바로 위 저항이 남아 있습니다. 거래량을 동반한 저항 돌파 또는 돌파 후 지지 전환을 기다리는 편이 강의의 원칙에 가깝습니다.'
    elif '회피' in result.entry_status:
        summary='현재는 신규 매수보다 추세 회복 확인이 우선입니다. 지지 회복, 이평선 배열 개선, 고저점 구조 전환이 나타나는지 관찰합니다.'
    else:
        summary='상승·하락 근거가 혼재합니다. 단일 신호에 반응하기보다 추가 신호가 같은 방향으로 중첩되는지 확인하는 구간입니다.'

    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(result.ticker)} 차트 분석</title><style>{_base_css()}</style></head><body><div class="wrap">
    <div class="top"><div><h1>{escape(result.ticker)} 차트 분석</h1><div class="sub">기준일 {escape(result.asof)} · 종가 {_fmt(result.close,2)} · 시장 {escape(result.market_regime)}</div></div><div class="hero-action">{escape(result.entry_status)}</div></div>
    <div class="grid">{score_cards}</div>
    <div class="card"><h2>최종 해석</h2><div class="summary">{escape(summary)}</div><div style="margin-top:10px">{_badge('종목상태 '+result.technical_grade,_score_class(result.technical_score))} {_badge('타이밍 '+result.timing_grade,_score_class(result.timing_score))} {_badge('위험 '+result.risk_level,_score_class(result.risk_score,True))} {_badge('추격위험 '+result.chase_risk,'bad' if result.chase_risk=='높음' else 'warn' if result.chase_risk=='보통' else 'good')}</div></div>
    <div class="two"><div class="card"><h2>종목 기술적 상태</h2>{tech_bars}</div><div class="card"><h2>현재 매수 타이밍</h2>{time_bars}</div></div>
    <div class="two"><div class="card"><h2>강점</h2><ul>{strengths}</ul></div><div class="card"><h2>위험·대기 사유</h2><ul>{risks}</ul></div></div>
    <div class="three"><div class="card"><h2>가격 레벨</h2><div class="kv"><b>지지선</b><span>{supports}</span><b>저항선</b><span>{resistances}</span></div></div><div class="card"><h2>위험관리</h2><div class="kv"><b>초기 손절 참고</b><span>{_fmt(result.stop_price,2)}</span><b>트레일링 참고</b><span>{_fmt(result.trailing_stop_price,2)}</span></div></div><div class="card"><h2>점수 의미</h2><div class="notice">Selection은 종목상태 55% + 매수타이밍 45%에서 고위험 패널티를 반영한 랭킹 점수입니다. Confluence는 강의의 7개 신호군 중첩 점수이며 상승확률 자체가 아닙니다.</div></div></div>
    <div class="card"><h2>분할진입 계획</h2><table><thead><tr><th>단계</th><th class="num">비중</th><th>확인 조건</th><th>현재</th></tr></thead><tbody>{plan_rows}</tbody></table></div>
    {chart_html}
    <div class="card"><h2>강의 신호 중첩 상세</h2><table><thead><tr><th>범주</th><th>신호</th><th class="num">점수</th><th>근거</th></tr></thead><tbody>{signal_rows}</tbody></table></div>
    <div class="card"><h2>주의사항</h2><ul>{notes}</ul><p class="notice">본 결과는 강의 내용을 정량화한 기술적 분석 도구이며 투자자문·수익 보장이 아닙니다. 기업·산업·매크로 분석과 별도 포지션 관리가 필요합니다.</p></div>
    </div></body></html>'''
    p.write_text(html,encoding='utf-8')



def _cap_fmt(v):
    if v is None:
        return '-'
    try:
        if pd.isna(v):
            return '-'
        return f'{float(v):,.0f}'
    except Exception:
        return escape(str(v))


def save_screen_html(df: pd.DataFrame, out_path: str):
    p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True)
    if df.empty:
        p.write_text('<html><meta charset="utf-8"><body><p>선별 결과 없음</p></body></html>',encoding='utf-8'); return
    has_meta = any(c in df.columns for c in ['name','market','market_cap','source_rank'])
    rows=[]
    for i,row in df.reset_index(drop=True).iterrows():
        action=str(row.get('action',''))
        ac='good' if ('분할진입' in action or '관심 진입' in action) else 'bad' if '회피' in action else 'warn'
        if has_meta:
            name=escape(str(row.get('name','')))
            ticker=escape(str(row.get('ticker','')))
            market=escape(str(row.get('market','')))
            source_rank=row.get('source_rank')
            source_rank='-' if pd.isna(source_rank) else int(source_rank)
            identity=f'<b>{name or ticker}</b><div class="sub">{ticker} · {market}</div>'
            prefix=(f'<td class="num">{i+1}</td>'
                    f'<td class="num">{source_rank}</td>'
                    f'<td>{identity}</td>'
                    f'<td class="num">{_cap_fmt(row.get("market_cap"))}</td>')
        else:
            prefix=f'<td class="num">{i+1}</td><td><b>{escape(str(row["ticker"]))}</b></td>'
        rows.append(
            f'<tr>{prefix}'
            f'<td class="num"><b>{float(row["score"]):.1f}</b></td>'
            f'<td class="num">{float(row["technical_score"]):.1f}</td>'
            f'<td class="num">{float(row["timing_score"]):.1f}</td>'
            f'<td class="num">{float(row["risk_score"]):.1f}</td>'
            f'<td>{_badge(row.get("chase_risk","-"),"bad" if row.get("chase_risk")=="높음" else "warn" if row.get("chase_risk")=="보통" else "good")}</td>'
            f'<td>{_badge(action,ac)}</td>'
            f'<td>{escape(str(row.get("market_regime","")))}</td>'
            f'<td class="num">{_fmt(row.get("close"),2)}</td></tr>'
        )
    avg=float(df['score'].mean()); top=int((df['timing_score']>=72).sum()); lowrisk=int((df['risk_score']<40).sum())
    if has_meta:
        headers='<th>순위</th><th>시총순위</th><th>종목</th><th>시가총액</th><th>Selection</th><th>Technical</th><th>Timing</th><th>Risk</th><th>추격</th><th>판단</th><th>시장상태</th><th>종가</th>'
        subtitle='KOSPI_Info.xlsx Universe에서 종목을 고른 뒤 좋은 종목과 지금 사기 좋은 종목을 분리해 평가'
    else:
        headers='<th>순위</th><th>종목</th><th>Selection</th><th>Technical</th><th>Timing</th><th>Risk</th><th>추격</th><th>판단</th><th>시장</th><th>종가</th>'
        subtitle='좋은 종목과 지금 사기 좋은 종목을 분리해 평가'
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>매수후보 랭킹</title><style>{_base_css()}</style></head><body><div class="wrap">
    <div class="top"><div><h1>기술적 매수 후보 랭킹</h1><div class="sub">{subtitle}</div></div></div>
    <div class="grid"><div class="score-card good"><div class="score-label">분석 성공</div><div class="score">{len(df)}</div></div><div class="score-card {_score_class(avg)}"><div class="score-label">평균 Selection</div><div class="score">{avg:.1f}</div></div><div class="score-card good"><div class="score-label">Timing ≥72</div><div class="score">{top}</div></div><div class="score-card good"><div class="score-label">Risk &lt;40</div><div class="score">{lowrisk}</div></div><div class="score-card warn"><div class="score-label">정렬 기준</div><div style="font-size:16px;font-weight:800;margin-top:10px">Selection → Timing</div></div></div>
    <div class="card"><div class="toolbar"><input id="q" placeholder="종목/판단 검색" oninput="filterRows()"></div><div style="overflow:auto"><table id="rank"><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>
    <div class="card"><p class="notice">시가총액·거래대금·거래량은 Universe 구성과 표시 용도로만 사용하며 기술적 점수에는 직접 넣지 않습니다. Selection은 중기 기술적 상태와 현재 매수 타이밍을 합성한 비교 점수입니다.</p></div></div>
    <script>function filterRows(){{const q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('#rank tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(q)?'':'none');}}</script></body></html>'''
    p.write_text(html,encoding='utf-8')
